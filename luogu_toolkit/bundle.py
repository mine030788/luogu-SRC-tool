"""bundle.py - 把 luogu 抓取数据打包成 ZIP, 供 luogu-report-generator 直接消费。

设计目标:
  项目 A (luogu-toolkit) 负责抓数据, 项目 B (luogu-report-generator) 只负责
  拼 prompt + 调 LLM + 出 PDF/HTML。两个项目之间用一个 ZIP 压缩包交换数据。

ZIP schema (schema_version=1):
  manifest.json           抓取元信息 (uid, username, generated_at, 文件清单)
  export_data.json        完整 export_data 字典 (与 web_app.py 写入的格式一致)
  items/                  拆开存每个题目的 record + 源码 (供排查 / 重跑用)

export_data 包含字段 (报告生成必需的):
  - student_info, solved_count, failed_count
  - summary (难度直方图 / 标签 / 算法标签)
  - passed_items, failed_items (含 record.sourceCode)
  - detail_fetch_stats
  - behavior_analysis (提交行为分析 + personality_scores)
  - syllabus_evaluation (大纲知识点对标)
  - six_dimension_scores (六维能力评分)
  - submission_evolution (v3.9.39 多版 diff, 可选, 缺失时报告自动兜底)
  - vjudge_data (跨平台数据, 缺失时报告用占位文案)

调用方式 (SDK):
    from luogu_toolkit import load_cookies
    from luogu_toolkit.bundle import build_report_zip
    cookies = load_cookies()
    zip_path = build_report_zip(cookies, output_dir=".", max_passed=10, max_failed=5)
    # → 落盘 luogu-SRC-<uid>-<ts>.zip, 返回路径

调用方式 (CLI):
    luogu-toolkit bundle --output ./
"""
from __future__ import annotations

import json
import logging
import os
import time
import zipfile
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter, defaultdict

from .cookie import CookieDict, load_cookies
from .syllabus_matcher import evaluate_all_topics

logger = logging.getLogger("luogu_toolkit.bundle")

# pyLuogu 已内嵌为 luogu_toolkit._pyluogu
try:
    from . import _pyluogu  # type: ignore
    _HAS_PYLUOGU = True
except Exception:  # pragma: no cover
    _pyluogu = None  # type: ignore
    _HAS_PYLUOGU = False

BUNDLE_SCHEMA_VERSION = 1

# 北京时区 helper
_BJ_TZ = timezone(timedelta(hours=8))

# 详情抓取的常量 (与 examples/export_for_ai.py 对齐)
DETAIL_FETCH_SAMPLE_LIMIT_PASSED = 30
DETAIL_FETCH_SAMPLE_LIMIT_FAILED = 20
DETAIL_FETCH_SLEEP_SECONDS = 1.8
DETAIL_FETCH_MAX_RETRIES = 5


def _require_pyluogu():
    if not _HAS_PYLUOGU:
        raise RuntimeError(
            "_pyluogu 子包不可用, 无法执行 bundle 操作。\n"
            "请检查 luogu_toolkit/_pyluogu/ 目录是否存在且完整"
        )


def _make_client(cookies: CookieDict) -> Any:
    _require_pyluogu()
    cookie_obj = _pyluogu.LuoguCookies(cookies)
    return _pyluogu.luoguAPI(cookies=cookie_obj)


# ═══════════════════════════════════════════════════════════════════════
#  行为分析 (从 behavior_analyzer.py 精简移植, 保持 schema 一致)
# ═══════════════════════════════════════════════════════════════════════

def _analyze_submission_behavior(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """精简版行为分析。返回与 behavior_analyzer.analyze_submission_behavior 同 schema。"""
    if not records:
        return {"error": "无提交记录"}

    total_records = len(records)
    status_counter: Counter = Counter()
    pid_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    hourly_distribution: Counter = Counter()
    weekday_distribution: Counter = Counter()
    daily_submit_count: Counter = Counter()
    daily_ac_count: Counter = Counter()
    ac_submit_distribution: Counter = Counter()  # AC 用了多少次提交

    for r in records:
        status = int(r.get("status") or 0)
        pid = (r.get("problem") or {}).get("pid") or ""
        submit_time = int(r.get("submitTime") or 0)
        score = r.get("score") or 0

        status_counter[status] += 1
        if pid:
            pid_records[pid].append(r)
        if submit_time:
            dt = datetime.fromtimestamp(submit_time, tz=_BJ_TZ)
            hourly_distribution[dt.hour] += 1
            weekday_distribution[dt.weekday()] += 1
            date_key = dt.strftime("%Y-%m-%d")
            daily_submit_count[date_key] += 1
            if status == 12:
                daily_ac_count[date_key] += 1

    # 1. AC 率
    ac_count = status_counter.get(12, 0)
    ac_rate = ac_count / total_records if total_records > 0 else 0.0

    # 一次 AC 率
    first_try_ac_count = 0
    total_tried_pids = len(pid_records)
    for pid, submits in pid_records.items():
        submits_sorted = sorted(submits, key=lambda x: int(x.get("submitTime") or 0))
        if submits_sorted and int(submits_sorted[0].get("status") or 0) == 12:
            first_try_ac_count += 1
        # AC 用了多少次提交
        ac_submits = [s for s in submits_sorted if int(s.get("status") or 0) == 12]
        if ac_submits:
            try_count = submits_sorted.index(ac_submits[0]) + 1
            ac_submit_distribution[try_count] += 1

    first_try_ac_rate = first_try_ac_count / total_tried_pids if total_tried_pids else 0.0

    # 死磕题
    stuck_pids = []
    max_submit_pid = None
    max_submit_count = 0
    for pid, submits in pid_records.items():
        cnt = len(submits)
        if cnt > max_submit_count:
            max_submit_count = cnt
            max_submit_pid = pid
        if cnt >= 3:
            ac_in_pid = sum(1 for s in submits if int(s.get("status") or 0) == 12)
            if ac_in_pid == 0:
                stuck_pids.append({
                    "pid": pid,
                    "title": (submits[0].get("problem") or {}).get("title", ""),
                    "submit_count": cnt,
                    "last_status": int(submits[-1].get("status") or 0),
                })
    stuck_pids.sort(key=lambda x: x["submit_count"], reverse=True)

    # 2. 时段分布
    time_slots = {
        "凌晨 (0-5点)": sum(hourly_distribution.get(h, 0) for h in range(0, 6)),
        "早晨 (6-9点)": sum(hourly_distribution.get(h, 0) for h in range(6, 10)),
        "上午 (9-12点)": sum(hourly_distribution.get(h, 0) for h in range(10, 13)),
        "下午 (13-17点)": sum(hourly_distribution.get(h, 0) for h in range(13, 18)),
        "傍晚 (17-20点)": sum(hourly_distribution.get(h, 0) for h in range(17, 21)),
        "晚上 (20-23点)": sum(hourly_distribution.get(h, 0) for h in range(20, 24)),
    }
    peak_hour = max(hourly_distribution.keys(), key=lambda h: hourly_distribution[h]) if hourly_distribution else None
    peak_hour_count = hourly_distribution[peak_hour] if peak_hour is not None else 0

    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_dist_named = {weekday_names[i]: weekday_distribution.get(i, 0) for i in range(7)}
    weekend_count = weekday_distribution.get(5, 0) + weekday_distribution.get(6, 0)
    weekday_count = sum(weekday_distribution.get(i, 0) for i in range(5))

    # 3. 活跃度
    active_days = len(daily_submit_count)
    total_days_span = 1
    if daily_submit_count:
        dates = sorted(daily_submit_count.keys())
        first_date = datetime.strptime(dates[0], "%Y-%m-%d")
        last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        total_days_span = max(1, (last_date - first_date).days + 1)
    active_rate = active_days / total_days_span if total_days_span > 0 else 0.0

    max_daily_submit = max(daily_submit_count.values()) if daily_submit_count else 0
    max_daily_date = max(daily_submit_count.keys(), key=lambda d: daily_submit_count[d]) if daily_submit_count else None
    consecutive_days = _max_consecutive_days(set(daily_submit_count.keys()))

    # 4. 编译错误
    ce_count = status_counter.get(3, 0) + status_counter.get(4, 0)
    ce_rate = ce_count / total_records if total_records > 0 else 0.0

    # 5. 调试耐心
    wa_resubmit_intervals: List[int] = []
    for pid, submits in pid_records.items():
        submits_sorted = sorted(submits, key=lambda x: int(x.get("submitTime") or 0))
        for i in range(1, len(submits_sorted)):
            prev = submits_sorted[i - 1]
            curr = submits_sorted[i]
            if int(prev.get("status") or 0) != 12:
                interval = int(curr.get("submitTime") or 0) - int(prev.get("submitTime") or 0)
                if 0 < interval < 3600:
                    wa_resubmit_intervals.append(interval)

    median_resubmit_interval = _median(wa_resubmit_intervals) if wa_resubmit_intervals else None
    quick_resubmit_rate = sum(1 for x in wa_resubmit_intervals if x < 60) / len(wa_resubmit_intervals) if wa_resubmit_intervals else 0.0

    result = {
        "total_records": total_records,
        "total_unique_problems": total_tried_pids,
        "ac_count": ac_count,
        "ac_rate": round(ac_rate, 3),
        "first_try_ac_rate": round(first_try_ac_rate, 3),
        "ce_count": ce_count,
        "ce_rate": round(ce_rate, 3),
        "status_distribution": dict(status_counter),
        "hourly_distribution": dict(hourly_distribution),
        "time_slot_distribution": time_slots,
        "peak_hour": peak_hour,
        "peak_hour_count": peak_hour_count,
        "weekday_distribution": weekday_dist_named,
        "weekend_vs_weekday": {"周末": weekend_count, "工作日": weekday_count},
        "active_days": active_days,
        "total_days_span": total_days_span,
        "active_rate": round(active_rate, 3),
        "max_daily_submits": max_daily_submit,
        "max_daily_date": max_daily_date,
        "max_consecutive_days": consecutive_days,
        "stuck_problems": stuck_pids[:10],
        "max_submit_single_problem": {"pid": max_submit_pid, "count": max_submit_count},
        "debug_patience": {
            "median_resubmit_interval_seconds": median_resubmit_interval,
            "quick_resubmit_under_60s_rate": round(quick_resubmit_rate, 3),
        },
        "ac_submit_distribution": dict(ac_submit_distribution),
    }
    result["personality_scores"] = _compute_personality_scores(result)
    return result


def _max_consecutive_days(date_strings: set) -> int:
    if not date_strings:
        return 0
    dates = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in date_strings)
    max_streak = 1
    current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 1
    return max_streak


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _compute_personality_scores(behavior_data: Dict[str, Any]) -> Dict[str, int]:
    """精简版性格画像 6 维评分 (0-100)。与 behavior_analyzer.compute_personality_scores 同 schema。"""
    scores: Dict[str, int] = {}

    stuck_problems = behavior_data.get("stuck_problems", [])
    ac_rate = behavior_data.get("ac_rate", 0) or 0
    first_try_rate = behavior_data.get("first_try_ac_rate", 0) or 0
    ce_rate = behavior_data.get("ce_rate", 0) or 0
    max_consecutive = behavior_data.get("max_consecutive_days", 0) or 0
    debug = behavior_data.get("debug_patience", {}) or {}
    quick_rate = debug.get("quick_resubmit_under_60s_rate", 0) or 0

    # 1. 坚韧度
    stuck_count = len(stuck_problems)
    max_stuck = max((p.get("submit_count", 0) for p in stuck_problems), default=0)
    avg_stuck = (
        sum(p.get("submit_count", 0) for p in stuck_problems) / stuck_count
        if stuck_count else 0
    )
    if max_stuck >= 20:
        base_pers = 70
    elif max_stuck >= 10:
        base_pers = 50
    elif max_stuck >= 5:
        base_pers = 38
    elif stuck_count >= 3:
        base_pers = 32
    else:
        base_pers = 18
    count_bonus = min(20, stuck_count * 4)
    avg_bonus = min(10, avg_stuck * 0.5)
    ac_factor = max(0.0, min(15.0, (ac_rate - 0.05) * 50))
    scores["坚韧度"] = int(max(0, min(100, base_pers + count_bonus + avg_bonus + ac_factor)))

    # 2. 完美主义
    first_try_score = first_try_rate * 55
    ce_penalty = ce_rate * 35
    not_rush_score = (1 - quick_rate) * 20
    scores["完美主义"] = int(max(0, min(100, first_try_score + not_rush_score - ce_penalty)))

    # 3. 冒险精神
    stuck_count_score = min(40, stuck_count * 8)
    hard_stuck = sum(1 for p in stuck_problems if p.get("submit_count", 0) >= 5)
    hard_score = min(30, hard_stuck * 10)
    scores["冒险精神"] = int(max(0, min(100, stuck_count_score + hard_score + 25)))

    # 4. 自律性
    hourly = behavior_data.get("hourly_distribution", {}) or {}
    total_h = sum(hourly.values()) or 1
    sorted_counts = sorted(hourly.values(), reverse=True) if hourly else []
    top1 = sorted_counts[0] if sorted_counts else 0
    top3 = sum(sorted_counts[:3])
    top3_share = top3 / total_h
    if top3_share >= 0.5:
        time_score = 55
    elif top3_share >= 0.4:
        time_score = 42
    elif top3_share >= 0.3:
        time_score = 30
    else:
        time_score = 20
    streak_score = min(25, max_consecutive * 3)
    scores["自律性"] = int(max(0, min(100, time_score + streak_score + 5)))

    # 5. 调试耐心
    median_interval = debug.get("median_resubmit_interval_seconds") or 60
    interval_score = min(50, median_interval / 6)  # 5min 满分 50
    not_rush = (1 - quick_rate) * 30
    scores["调试耐心"] = int(max(0, min(100, interval_score + not_rush + 10)))

    # 6. 作息规律
    weekend_count = behavior_data.get("weekend_vs_weekday", {}).get("周末", 0)
    weekday_count = behavior_data.get("weekend_vs_weekday", {}).get("工作日", 0)
    total = (weekend_count + weekday_count) or 1
    weekday_share = weekday_count / total
    balance_score = min(40, (1 - abs(weekday_share - 0.7)) * 100)
    peak_h = behavior_data.get("peak_hour")
    if peak_h is not None and 8 <= peak_h <= 22:
        peak_score = 30
    elif peak_h is not None and (6 <= peak_h <= 23):
        peak_score = 18
    else:
        peak_score = 5
    scores["作息规律"] = int(max(0, min(100, balance_score + peak_score + 5)))

    return scores


# ═══════════════════════════════════════════════════════════════════════
#  六维评分 (从 behavior_analyzer.compute_six_dimension_scores 精简移植)
# ═══════════════════════════════════════════════════════════════════════

def _compute_six_dimension_scores(export_data: Dict[str, Any], behavior_data: Dict[str, Any]) -> Dict[str, int]:
    summary = export_data.get("summary", {}) or {}
    top_tags = summary.get("top_algorithm_tags", []) or summary.get("top_tags", []) or []
    difficulty_histogram = summary.get("difficulty_histogram", {}) or {}

    difficulty_total = 0
    weighted = 0
    for key, value in difficulty_histogram.items():
        if str(key).isdigit():
            difficulty_total += int(value)
            weighted += int(key) * int(value)
    avg_difficulty = weighted / difficulty_total if difficulty_total else 0

    tag_counts: Dict[str, int] = {}
    for item in top_tags:
        tag_name = str(item.get("name") or "").lower()
        tag_counts[tag_name] = int(item.get("count", 0))

    def _count_tags(*keywords) -> int:
        total = 0
        for tag_name, count in tag_counts.items():
            if any(kw in tag_name for kw in keywords):
                total += count
        return total

    basic_algo = _count_tags("枚举", "模拟", "贪心", "递归", "二分", "排序", "分治", "倍增", "前缀和", "差分")
    search = _count_tags("搜索", "dfs", "bfs", "回溯", "剪枝", "记忆化")
    dp = _count_tags("dp", "动态规划", "背包", "区间", "树形", "状压", "数位", "期望")
    graph = _count_tags("图", "最短路", "并查集", "拓扑", "tarjan", "lca", "网络流", "匹配", "二分图",
                        "图遍历", "树的遍历", "树的直径", "树的重心", "基环树")
    ds = _count_tags("线段树", "树状数组", "st表", "单调", "堆", "平衡树", "分块", "莫队", "链表", "栈", "队列")
    string = _count_tags("字符串", "kmp", "hash", "trie", "sam", "manacher", "ac自动机")
    math_tags = _count_tags("数论", "数学", "组合", "计数", "概率", "矩阵", "快速幂", "逆元", "欧拉", "gcd", "筛法")

    score_basic = min(95, 40 + basic_algo * 2 + search * 2 + int(avg_difficulty * 5))
    score_ds = min(95, 30 + ds * 3 + int(avg_difficulty * 4))
    score_graph = min(95, 30 + graph * 3 + int(avg_difficulty * 4))
    score_dp = min(95, 35 + dp * 3 + int(avg_difficulty * 5))
    score_string = min(95, 25 + string * 4 + int(avg_difficulty * 3))
    score_math = min(95, 20 + math_tags * 3 + int(avg_difficulty * 3))

    ac_rate = behavior_data.get("ac_rate", 0.5)
    first_try_rate = behavior_data.get("first_try_ac_rate", 0.5)
    adjustment = int((ac_rate + first_try_rate - 1.0) * 10)

    return {
        "基础算法": max(20, min(95, score_basic + adjustment)),
        "数据结构": max(20, min(95, score_ds + adjustment)),
        "图论": max(20, min(95, score_graph + adjustment)),
        "动态规划": max(20, min(95, score_dp + adjustment)),
        "字符串": max(20, min(95, score_string + adjustment)),
        "数学": max(20, min(95, score_math + adjustment)),
    }

# ═══════════════════════════════════════════════════════════════════════
#  主流程: build_export_data + build_report_zip
# ═══════════════════════════════════════════════════════════════════════

def _problem_to_json(problem: Any) -> Dict[str, Any]:
    """把 pyLuogu.ProblemSummary 统一转 dict"""
    try:
        return dict(problem)
    except Exception:
        out: Dict[str, Any] = {}
        for attr in ("pid", "title", "difficulty", "type", "tags", "totalSubmit",
                     "totalAccepted", "flag", "fullScore"):
            if hasattr(problem, attr):
                out[attr] = getattr(problem, attr)
        return out


def _pick_record_for_problem(
    luogu: Any,
    uid: int,
    pid: str,
    max_records_to_try: int,
    *,
    require_source_code: bool = True,
) -> Optional[Dict[str, Any]]:
    """精简版 _pick_record_for_problem。返回 dict 或 None。"""
    try:
        record_list = luogu.get_record_list(page=1, uid=uid, pid=pid, user=str(uid))
    except Exception as e:
        return {"error": f"record list fetch failed: {str(e)[:200]}", "pid": pid}

    records = []
    if hasattr(record_list, "records") and record_list.records is not None:
        records = list(record_list.records)
    elif isinstance(record_list, dict):
        records = record_list.get("records", [])
    if not records:
        return None

    tried = 0
    for record in records:
        if tried >= max_records_to_try:
            break
        tried += 1
        try:
            summary = record.to_json() if hasattr(record, "to_json") else dict(record)
        except Exception:
            summary = {"id": getattr(record, "id", "")}
        summary.setdefault("sourceCode", None)
        if not require_source_code:
            return summary
        try:
            detail = luogu.get_record(str(record.id)).record
            detail_json = detail.to_json() if hasattr(detail, "to_json") else dict(detail)
            code = getattr(detail, "sourceCode", None)
            detail_json["sourceCode"] = code
            if code:
                return detail_json
        except Exception as e:
            summary["_detail_error"] = str(e)[:200]
            if "auth" in str(e).lower() or "login" in str(e).lower():
                # 鉴权失败, 别再试了
                return summary
        time.sleep(0.3)
    return summary if "summary" in dir() else None


def _index_local_code(code_dir: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """扫本地代码目录, 按文件名 (P1234) / 路径包含 (P1234) 索引。"""
    if not code_dir:
        return {}
    code_path = Path(code_dir)
    if not code_path.exists():
        return {}
    import re
    pid_pattern = re.compile(r"\bP?\d{3,5}\b", re.IGNORECASE)
    index: Dict[str, Dict[str, Any]] = {}
    for f in code_path.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {".cpp", ".cc", ".cxx", ".c", ".py", ".pas", ".java", ".go", ".rs"}:
            continue
        m = pid_pattern.search(f.stem)
        if not m:
            continue
        pid = m.group(0).upper()
        if not pid.startswith("P"):
            pid = "P" + pid
        index[pid] = {"path": str(f), "mtime": f.stat().st_mtime}
    return index


def _build_summary(problems: List[Any], tag_by_id: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """简化版 summary (难度直方图 + top_algorithm_tags + top_tags + level_experience)

    v3.9.78 · 4 道题知识点全空白修复：
    旧逻辑只统计 type==2 的算法标签，4 道题若没有 algorithm-type 标签，
    top_algorithm_tags 为空 → 知识点覆盖全 0。增加 fallback_tag_counter，
    把 type=1（功能/分类）+ type=2（算法）都纳入对标范围。
    """
    difficulty_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    algorithm_tag_counter: Counter = Counter()
    fallback_tag_counter: Counter = Counter()  # v3.9.78 · type in {1,2}
    tag_type_counter: Counter = Counter()

    for p in problems:
        d = getattr(p, "difficulty", None)
        if d is not None:
            difficulty_counter[int(d)] += 1
        for tag_id in list(getattr(p, "tags", []) or []):
            tag_counter[int(tag_id)] += 1
            tag = tag_by_id.get(int(tag_id), {})
            ttype = tag.get("type")
            if ttype is not None:
                tag_type_counter[int(ttype)] += 1
                if int(ttype) == 2:
                    algorithm_tag_counter[int(tag_id)] += 1
                # v3.9.78 · 兜底：type=1（功能/分类）和 type=2（算法）都属于"可对标知识点"范围
                if int(ttype) in (1, 2):
                    fallback_tag_counter[int(tag_id)] += 1

    top_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:30]
    # v3.9.78 · 知识点对标用：优先 algorithm-type，回退到 type in {1,2}
    if algorithm_tag_counter:
        _src = algorithm_tag_counter
    else:
        _src = fallback_tag_counter
    top_algorithm_tags = sorted(_src.items(), key=lambda x: x[1], reverse=True)[:30]

    def _name(tid: int) -> str:
        return tag_by_id.get(tid, {}).get("name", f"#{tid}")

    return {
        "difficulty_histogram": dict(difficulty_counter),
        "top_tags": [{"id": tid, "name": _name(tid), "count": cnt} for tid, cnt in top_tags],
        "top_algorithm_tags": [{"id": tid, "name": _name(tid), "count": cnt} for tid, cnt in top_algorithm_tags],
        "tag_type_distribution": dict(tag_type_counter),
        "level_experience": {},  # 简化: 不算
        "total_problems": len(problems),
    }


def build_export_data(
    cookies: CookieDict,
    *,
    max_passed: int = 30,
    max_failed: int = 10,
    max_records_per_problem: int = 3,
    code_dir: Optional[str] = None,
    fetch_evolution: bool = False,
    on_progress: Optional[Any] = None,
) -> Dict[str, Any]:
    """抓取并组装完整的 export_data 字典。

    Parameters
    ----------
    cookies : CookieDict
    max_passed : int — 最多取多少道已通过的题
    max_failed : int — 最多取多少道做错/未通过的题
    max_records_per_problem : int — 每题最多翻多少条 record 找源码
    code_dir : str, optional — 本地代码目录, 用于补全 sourceCode (离线场景)
    fetch_evolution : bool — 是否拉多版 diff (默认 False, 报告侧可省略)
    on_progress : callable, optional — 进度回调 fn(stage: str, current: int, total: int, message: str)

    Returns
    -------
    dict — 完整的 export_data, 与 web_app.py 写入的格式一致
    """
    _require_pyluogu()
    client = _make_client(cookies)
    me = client.me()
    uid = int(me.uid)

    def _p(stage: str, current: int = 0, total: int = 0, message: str = "") -> None:
        if on_progress:
            try:
                on_progress(stage, current, total, message)
            except Exception:
                pass
        logger.info("[%s] %d/%d %s", stage, current, total, message)

    _p("init", 0, 0, f"已登录 uid={uid}")

    # 1. tags
    tag_by_id: Dict[int, Dict[str, Any]] = {}
    try:
        tag_resp = client.get_tags()
        for t in tag_resp.tags:
            tag_by_id[t.id] = {"id": t.id, "name": t.name, "type": t.type, "parent": t.parent}
    except Exception as e:
        logger.warning("get_tags failed: %s", e)

    # 2. practice
    _p("practice", 0, 0, "拉取做题记录")
    practice = client.get_user_practice(uid)
    raw = practice.data if isinstance(practice.data, dict) else None
    passed = raw.get("passed") if isinstance(raw, dict) else None
    solved_problems: List[Any] = []
    if isinstance(passed, list):
        # 用 _pyluogu.ProblemSummary 包一下保持 schema 一致
        for item in passed:
            if not isinstance(item, dict):
                continue
            pid = item.get("pid")
            if not pid:
                continue
            solved_problems.append(_pyluogu.ProblemSummary({
                "pid": str(pid),
                "title": item.get("title") or item.get("name") or "",
                "difficulty": item.get("difficulty"),
                "type": item.get("type"),
                "submitted": True,
                "accepted": True,
                "tags": [],
                "totalSubmit": None,
                "totalAccepted": None,
                "flag": None,
                "fullScore": None,
            }))
    else:
        solved_problems = list(practice.problems)
    solved_problems.sort(key=lambda p: (p.difficulty if p.difficulty is not None else 10, p.pid))
    all_passed = solved_problems[: max(0, int(max_passed))]

    # 3. failed problems - 简化: 从 practice.problems 里筛 (实际洛谷不直接给 failed 列表)
    #    兜底: 从 record_list 翻几页找 status!=12 的 pid
    _p("failed", 0, 0, "拉取失败/未通过题")
    all_failed: List[Any] = []
    try:
        failed_seen: set = set()
        for page in range(1, 4):
            try:
                rl = client.get_record_list(page=page, user=str(uid))
            except Exception:
                break
            page_records = []
            if hasattr(rl, "records") and rl.records is not None:
                page_records = list(rl.records)
            elif isinstance(rl, dict):
                page_records = rl.get("records", [])
            for r in page_records:
                if int(r.status or 0) == 12:
                    continue
                pid = (r.problem.pid if hasattr(r, "problem") and r.problem else None) or r.get("problem", {}).get("pid")
                if not pid or pid in failed_seen:
                    continue
                failed_seen.add(pid)
                title = (r.problem.title if hasattr(r, "problem") and r.problem else None) or r.get("problem", {}).get("title", "")
                all_failed.append(_pyluogu.ProblemSummary({
                    "pid": str(pid), "title": str(title), "difficulty": None,
                    "type": None, "submitted": True, "accepted": False, "tags": [],
                    "totalSubmit": None, "totalAccepted": None, "flag": None, "fullScore": None,
                }))
                if len(all_failed) >= max_failed:
                    break
            if len(all_failed) >= max_failed:
                break
    except Exception as e:
        logger.warning("failed problems scan: %s", e)
    all_failed = all_failed[: max(0, int(max_failed))]

    # 4. local code index
    local_code_index = _index_local_code(code_dir)

    # 5. 抓每道 passed 的 record + 源码
    _p("passed_items", 0, len(all_passed), "抓取已通过的题源码")
    passed_items: List[Dict[str, Any]] = []
    detail_fetch_state: Dict[str, Any] = {}
    for idx, problem in enumerate(all_passed, start=1):
        _p("passed_items", idx, len(all_passed), f"{problem.pid} {problem.title}")
        record: Optional[Dict[str, Any]] = None
        require_code = idx <= DETAIL_FETCH_SAMPLE_LIMIT_PASSED
        if not detail_fetch_state.get("stop_detail_fetch"):
            try:
                record = _pick_record_for_problem(
                    client, uid, problem.pid, max_records_per_problem,
                    require_source_code=require_code,
                )
            except Exception as e:
                record = {"error": str(e)[:200], "pid": problem.pid}
        else:
            record = {"sourceCode": None, "_detail_skipped": "circuit broken"}

        local_meta = local_code_index.get(problem.pid.upper())
        local_code = None
        if local_meta:
            try:
                content = Path(local_meta["path"]).read_text(encoding="utf-8", errors="replace")
                if len(content) > 4000:
                    content = content[:4000]
                local_code = {"source": "local", "path": local_meta["path"],
                              "mtime": local_meta["mtime"], "content": content}
            except Exception:
                pass
            # 用本地代码补 sourceCode
            if isinstance(record, dict) and not record.get("sourceCode") and content:
                record["sourceCode"] = content
                record["_source"] = "local"

        passed_items.append({
            "problem": _problem_to_json(problem),
            "record": record,
            "local_code": local_code,
        })
        time.sleep(0.4)

    # 6. failed items
    _p("failed_items", 0, len(all_failed), "抓取失败的题源码")
    failed_items: List[Dict[str, Any]] = []
    for idx, problem in enumerate(all_failed, start=1):
        _p("failed_items", idx, len(all_failed), f"{problem.pid} {problem.title}")
        record: Optional[Dict[str, Any]] = None
        require_code = idx <= DETAIL_FETCH_SAMPLE_LIMIT_FAILED
        if not detail_fetch_state.get("stop_detail_fetch"):
            try:
                record = _pick_record_for_problem(
                    client, uid, problem.pid, max_records_per_problem,
                    require_source_code=require_code,
                )
            except Exception as e:
                record = {"error": str(e)[:200], "pid": problem.pid}
        else:
            record = {"sourceCode": None, "_detail_skipped": "circuit broken"}

        local_meta = local_code_index.get(problem.pid.upper())
        local_code = None
        if local_meta:
            try:
                content = Path(local_meta["path"]).read_text(encoding="utf-8", errors="replace")
                if len(content) > 4000:
                    content = content[:4000]
                local_code = {"source": "local", "path": local_meta["path"],
                              "mtime": local_meta["mtime"], "content": content}
            except Exception:
                pass
            if isinstance(record, dict) and not record.get("sourceCode") and content:
                record["sourceCode"] = content
                record["_source"] = "local"

        failed_items.append({
            "problem": _problem_to_json(problem),
            "record": record,
            "local_code": local_code,
        })
        time.sleep(0.4)

    # 7. summary
    summary = _build_summary(all_passed, tag_by_id)

    # 7.5 构造 tag → 题目难度列表 (供 syllabus_matcher 算每个知识点平均难度)
    tag_difficulty_map: Dict[str, List[int]] = {}
    for prob in all_passed:
        d = getattr(prob, "difficulty", None)
        if d is None or d <= 0:
            continue
        try:
            di = int(d)
        except (TypeError, ValueError):
            continue
        for tag_id in list(getattr(prob, "tags", []) or []):
            try:
                tid = int(tag_id)
            except (TypeError, ValueError):
                continue
            tag_name = str(tag_by_id.get(tid, {}).get("name") or "").strip()
            if not tag_name:
                continue
            tag_difficulty_map.setdefault(tag_name, []).append(di)

    # 8. detail_fetch_stats (精简)
    detail_fetch_stats = {
        "total": len(passed_items) + len(failed_items),
        "with_source": sum(
            1 for it in passed_items + failed_items
            if isinstance(it.get("record"), dict) and it["record"].get("sourceCode")
        ),
        "missing_source": sum(
            1 for it in passed_items + failed_items
            if not (isinstance(it.get("record"), dict) and it["record"].get("sourceCode"))
        ),
    }

    # 9. 行为分析: 拉最近 25 页 record_list (~ 1250 条)
    _p("behavior", 0, 0, "拉取提交记录做行为分析")
    behavior_records: List[Dict[str, Any]] = []
    try:
        for page in range(1, 26):
            try:
                rl = client.get_record_list(page=page, user=str(uid))
            except Exception:
                break
            page_records = []
            if hasattr(rl, "records") and rl.records is not None:
                page_records = list(rl.records)
            elif isinstance(rl, dict):
                page_records = rl.get("records", [])
            for r in page_records:
                try:
                    behavior_records.append(r.to_json() if hasattr(r, "to_json") else dict(r))
                except Exception:
                    pass
            if len(behavior_records) >= 1200:
                break
            time.sleep(0.2)
    except Exception as e:
        logger.warning("behavior records scan: %s", e)

    behavior_data = _analyze_submission_behavior(behavior_records)

    # 10. six_dimension_scores
    _p("scores", 0, 0, "计算六维评分")
    six_dim_scores = _compute_six_dimension_scores(
        {"solved_count": len(all_passed), "failed_count": len(all_failed), "summary": summary},
        behavior_data,
    )

    # 11. syllabus_evaluation
    _p("syllabus", 0, 0, "计算大纲对标")
    syllabus_evaluation = evaluate_all_topics(
        summary.get("top_algorithm_tags", []) or summary.get("top_tags", []) or [],
        tag_difficulty_map=tag_difficulty_map,
    )

    # 12. submission_evolution (可选, 默认不抓, 让报告侧兜底)
    submission_evolution: Dict[str, Any] = {
        "selected_problems": [],
        "summary": {"error": "bundle 阶段未拉取, 报告侧用 prompt 兜底文案"},
    }

    # 13. vjudge_data (本项目不抓, 给个 null 占位)
    vjudge_data: Dict[str, Any] = {"linked": False, "username": "", "note": "bundle 阶段未抓 vjudge"}

    # 14. student_info
    student_info = {
        "name": getattr(me, "name", "") or getattr(me, "username", ""),
        "username": getattr(me, "username", ""),
        "school": "",
        "grade": "",
        "grade_zh": "",
        "eval_time": datetime.now(tz=_BJ_TZ).strftime("%Y-%m-%d %H:%M"),
        "luogu_uid": uid,
    }

    export_data: Dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "student_info": student_info,
        "solved_count": len(all_passed),
        "failed_count": len(all_failed),
        "summary": summary,
        "passed_items": passed_items,
        "failed_items": failed_items,
        "detail_fetch_stats": detail_fetch_stats,
        "behavior_analysis": behavior_data,
        "syllabus_evaluation": syllabus_evaluation,
        "six_dimension_scores": six_dim_scores,
        "submission_evolution": submission_evolution,
        "vjudge_data": vjudge_data,
        "tags": {"by_id": {str(k): v for k, v in tag_by_id.items()}, "types_by_id": {}},
    }

    _p("done", len(passed_items), len(passed_items) + len(failed_items),
       f"完成: 通过 {len(passed_items)} 失败 {len(failed_items)}")
    return export_data


def build_report_zip(
    cookies: Optional[CookieDict] = None,
    *,
    output_dir: str = ".",
    filename_prefix: str = "luogu-SRC",
    max_passed: int = 30,
    max_failed: int = 10,
    max_records_per_problem: int = 3,
    code_dir: Optional[str] = None,
    export_data: Optional[Dict[str, Any]] = None,
    on_progress: Optional[Any] = None,
) -> Path:
    """拉取数据并打成 ZIP, 返回落盘路径。

    - cookies=None: 从默认 cookies.json 读
    - export_data=...: 跳过抓取, 直接用传入的 dict 打包 (调试 / 单元测试用)
    """
    if export_data is None:
        if cookies is None:
            cookies = load_cookies()
        export_data = build_export_data(
            cookies,
            max_passed=max_passed,
            max_failed=max_failed,
            max_records_per_problem=max_records_per_problem,
            code_dir=code_dir,
            on_progress=on_progress,
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    uid = export_data.get("student_info", {}).get("luogu_uid") or export_data.get("student_info", {}).get("uid") or "user"
    ts = datetime.now(tz=_BJ_TZ).strftime("%Y%m%d-%H%M%S")
    filename = f"{filename_prefix}-{uid}-{ts}.zip"
    out_path = out_dir / filename

    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "luogu_uid": uid,
        "username": export_data.get("student_info", {}).get("username", ""),
        "name": export_data.get("student_info", {}).get("name", ""),
        "generated_at": int(time.time()),
        "generated_at_iso": datetime.now(tz=_BJ_TZ).isoformat(),
        "toolkit_version": "luogu-toolkit/0.1.0",
        "solved_count": export_data.get("solved_count", 0),
        "failed_count": export_data.get("failed_count", 0),
        "files": ["export_data.json", "items/"],
    }

    # 写 items/ 子目录 (拆开存每道题, 方便报告侧 / 排查用)
    items_buf: Dict[str, bytes] = {}
    for kind, items in (("passed", export_data.get("passed_items", [])),
                         ("failed", export_data.get("failed_items", []))):
        for it in items:
            problem = it.get("problem") or {}
            pid = str(problem.get("pid") or "unknown").replace("/", "_")
            items_buf[f"items/{kind}/{pid}.json"] = json.dumps(
                it, ensure_ascii=False, indent=2
            ).encode("utf-8")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        zf.writestr("export_data.json",
                    json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"))
        for name, data in items_buf.items():
            zf.writestr(name, data)

    logger.info("Bundle written: %s (%.1f KB)",
                out_path, out_path.stat().st_size / 1024)
    return out_path


def load_export_data_from_zip(zip_path: str | Path) -> Dict[str, Any]:
    """工具函数: 从 ZIP 读出 export_data (供报告侧或调试用)。

    报告侧 (luogu-report-generator) 用法:
        from luogu_toolkit.bundle import load_export_data_from_zip
        export_data = load_export_data_from_zip("uploaded.zip")
        md = generate_ai_report(export_data, ...)
    """
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        with zf.open("export_data.json") as f:
            return json.loads(f.read().decode("utf-8"))


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "build_export_data",
    "build_report_zip",
    "load_export_data_from_zip",
]
