from typing import Literal

ResponseType = Literal["json", "bytes", "text", "response"]

from .types import (
    ActivityReuqestParams,
    ContestListRequestParams,
    DiscussionRequestParams,
    ListRequestParams,
    ProblemListRequestParams,
    ProblemRequestParams,
    ProblemSetListRequestParams,
    ProblemSetType,
    ProblemType,
    TeamProblemListRequestParams,
    TransferProblemType,
    RequestParams,
    UserListRequestParams,
)


class RawRequestParams(RequestParams):
    def __init__(self, json: dict[str, object]):
        self._json = {key: value for key, value in json.items() if value is not None}

    def to_json(self):
        return self._json


PROBLEM_LIST_ENDPOINT = "problem/list"
PROBLEM_NEW_ENDPOINT = "fe/api/problem/new"
TAGS_ENDPOINT = "/_lfe/tags"
ACTIVITY_ENDPOINT = "/api/feed/list"
PROBLEM_SET_LIST_ENDPOINT = "training/list"
CONTEST_LIST_ENDPOINT = "contest/list"
USER_SEARCH_ENDPOINT = "api/user/search"
CREATED_PROBLEMS_ENDPOINT = "api/user/createdProblems"
CREATED_PROBLEM_SETS_ENDPOINT = "api/user/createdTrainings"
CREATED_CONTESTS_ENDPOINT = "api/user/createdContests"

ROUTES = {
    "feed_watching": "api/feed/watching",
    "feed_list": "api/feed/list",
    "feed_post": "api/feed/postBenben",
    "feed_delete": "api/feed/delete/{id}",
    "feed_report": "api/report/feed",
    "article_list": "article",
    "article": "article/{lid}",
    "article_find": "api/article/find",
    "article_mine": "article/mine",
    "article_favored": "article/favored",
    "article_collection": "article/collection/{id}",
    "article_available_collection": "article/{lid}/availableCollection",
    "article_new": "api/article/new",
    "article_edit": "api/article/edit/{lid}",
    "article_delete": "api/article/delete/{lid}",
    "article_batch_edit": "api/article/batchEdit",
    "article_favor": "api/article/favor/{lid}",
    "article_vote": "api/article/vote/{lid}",
    "article_request_promotion": "api/article/requestPromotion/{lid}",
    "article_withdraw_promotion": "api/article/withdrawPromotion/{lid}",
    "article_replies": "article/{lid}/replies",
    "article_reply": "article/{lid}/reply",
    "article_delete_reply": "article/{lid}/deleteReply/{id}",
    "captcha_lg4": "lg4/captcha",
    "auth_motp_to": "auth/motp/to",
    "auth_finish_signup": "auth/finish-signup",
    "auth_password": "do-auth/password",
    "openid_connect": "openid/{id}/connect",
    "auth_logout": "auth/logout",
    "auth_lock": "auth/lock",
    "auth_totp": "do-auth/totp",
    "auth_motp_request": "auth/motp/request",
    "auth_motp": "do-auth/motp",
    "auth_unlock": "auth/unlock",
    "blog_user_blogs": "api/blog/userBlogs",
    "blog_lists": "api/blog/lists",
    "blog_detail": "api/blog/detail/{id}",
    "blog_new": "blogAdmin/article/post_new",
    "blog_edit": "blogAdmin/article/post_edit/{id}",
    "blog_delete": "api/blog/delete/{id}",
    "blog_admin_list": "blogAdmin/article/list",
    "blog_replies": "api/blog/replies/{id}",
    "blog_reply": "api/blog/reply/{id}",
    "blog_vote": "api/blog/vote/{id}",
    "blog_delete_comment": "blogAdmin/article/deleteComment/{id}",
    "chat": "chat",
    "chat_record": "api/chat/record",
    "chat_new": "api/chat/new",
    "chat_delete": "api/chat/delete",
    "chat_clear_unread": "api/chat/clearUnread",
    "joined_contests": "api/user/joinedContests",
    "contest_list": "contest/list",
    "contest": "contest/{id}",
    "created_contests": "api/user/createdContests",
    "contest_created": "contest/edit/{id}",
    "contest_scoreboard": "fe/api/contest/scoreboard/{id}",
    "contest_join": "contest/{id}/join",
    "contest_squad": "contest/{id}/squad",
    "contest_squad_member_quit": "contest/{id}/squadMemberQuit",
    "contest_new": "fe/api/contest/new",
    "contest_edit": "fe/api/contest/edit/{id}",
    "contest_edit_problem": "fe/api/contest/editProblem/{id}",
    "contest_delete": "fe/api/contest/delete/{id}",
    "discuss_list": "discuss",
    "discuss": "discuss/{id}",
    "created_posts": "api/user/createdPosts",
    "discuss_post": "api/discuss/post",
    "discuss_reply": "api/discuss/reply/{id}",
    "discuss_delete": "api/discuss/delete/{id}",
    "discuss_delete_reply": "api/discuss/deleteReply/{id}",
    "post_report": "api/report/post",
    "post_reply_report": "api/report/post_reply",
    "ide_submit": "api/ide_submit",
    "image_list": "image",
    "image_detail": "api/image/detail/{id}",
    "image_generate_upload_link": "api/image/generateUploadLink",
    "image_delete": "api/image/delete",
    "config": "_lfe/config",
    "ranking": "ranking",
    "ranking_elo": "ranking/elo",
    "notification": "user/notification",
    "advertisement": "api/qiaFan/getFan/{id}",
    "paintboard_board": "paintboard/board",
    "paintboard_reset_token": "paintboard/resetToken",
    "paintboard_paint": "paintboard/paint",
    "paste_list": "paste",
    "paste": "paste/{id}",
    "paste_new": "paste/new",
    "paste_edit": "paste/edit/{id}",
    "paste_delete": "paste/delete/{id}",
    "marked_trainings": "api/user/markedTrainings",
    "training_list": "training/list",
    "training": "training/{id}",
    "created_trainings": "api/user/createdTrainings",
    "training_mark": "api/training/mark/{id}",
    "training_unmark": "api/training/unmark/{id}",
    "training_new": "api/training/new",
    "training_edit": "api/training/edit/{id}",
    "training_add_problem": "api/training/addProblem/{id}",
    "training_edit_problems": "api/training/editProblems/{id}",
    "training_clone": "api/training/clone/{id}",
    "training_delete": "api/training/delete/{id}",
    "problem_tasklist_add": "fe/api/problem/tasklistAdd",
    "problem_tasklist_remove": "fe/api/problem/tasklistRemove",
    "problem_list": "problem/list",
    "problem": "problem/{pid}",
    "problem_solution": "problem/solution/{pid}",
    "problem_submit": "fe/api/problem/submit/{pid}",
    "problem_new": "fe/api/problem/new",
    "problem_edit": "fe/api/problem/edit/{pid}",
    "problem_edit_testcase": "fe/api/problem/editTestCase/{pid}",
    "problem_transfer": "fe/api/problem/transfer/{pid}",
    "problem_delete": "fe/api/problem/delete/{id}",
    "created_problems": "api/user/createdProblems",
    "problem_translate": "fe/api/problem/translate/{pid}",
    "record_list": "record/list",
    "record": "record/{id}",
    "record_downloadable_testcase": "fe/api/record/queryDownloadableTestcase/{id}",
    "record_download_testcase": "fe/api/record/downloadTestcase/{id}",
    "mine_team": "user/mine/team",
    "team": "team/{id}",
    "team_member_page": "team/{id}/member",
    "team_problem_page": "team/{id}/problem",
    "team_training_page": "team/{id}/training",
    "team_contest_page": "team/{id}/contest",
    "team_join": "api/team/join/{id}",
    "team_exit": "api/team/exit/{id}",
    "team_create": "api/team/create",
    "team_edit": "api/team/edit/{id}",
    "team_set_master": "api/team/setMaster/{id}",
    "team_edit_notice": "api/team/editNotice/{id}",
    "team_edit_member": "api/team/editMember/{id}",
    "team_review": "api/team/review/{id}",
    "team_kick": "api/team/kick/{id}",
    "theme_list": "theme/list",
    "theme_design": "theme/design/{id}",
    "theme_set": "theme/setTheme/{id}",
    "theme_new": "theme/edit/",
    "theme_edit": "theme/edit/{id}",
    "theme_delete": "theme/delete/{id}",
    "user_practice": "user/{uid}/practice",
    "user": "user/{uid}",
    "user_search": "api/user/search",
    "user_followings": "api/user/followings",
    "user_followers": "api/user/followers",
    "user_blacklist": "api/user/blacklist",
    "rating_elo": "api/rating/elo",
    "user_setting": "user/setting",
    "user_preference": "user/setting/preference",
    "user_preference_update": "user/setting/preference/update",
    "user_prize_setting": "user/setting/prize",
    "user_security_setting": "user/setting/security",
    "user_update_slogan": "api/user/updateSlogan",
    "user_update_introduction": "api/user/updateIntroduction",
    "user_update_header_image": "api/user/updateHeaderImage",
    "user_bind_vjudge": "api/user/bindVjudgeAccount",
    "user_unbind_vjudge": "api/user/unbindVjudgeAccount",
    "openid_bind": "openid/{id}/bind",
    "user_unbind_openid": "api/user/unbindOpenId/{id}",
    "tags": "_lfe/tags",
}


def api_route(name: str, **path_params: object) -> str:
    return ROUTES[name].format(**path_params)


def raw_params(**params: object) -> RequestParams:
    return RawRequestParams(json=params)


def problem_endpoint(pid: str) -> str:
    return f"problem/{pid}"


def problem_settings_legacy_endpoint(pid: str) -> str:
    return f"problem/edit/{pid}"


def problem_settings_endpoint(pid: str) -> str:
    return f"problem/{pid}/edit"


def problem_edit_endpoint(pid: str) -> str:
    return f"fe/api/problem/edit/{pid}"


def problem_edit_testcase_endpoint(pid: str) -> str:
    return f"/fe/api/problem/editTestCase/{pid}"


def problem_delete_endpoint(pid: str) -> str:
    return f"fe/api/problem/delete/{pid}"


def problem_transfer_endpoint(pid: str) -> str:
    return f"fe/api/problem/transfer/{pid}"


def problem_solution_endpoint(pid: str) -> str:
    return f"problem/solution/{pid}"


def problem_submit_endpoint(pid: str) -> str:
    return f"/fe/api/problem/submit/{pid}"


def user_endpoint(uid: int | str) -> str:
    return f"user/{uid}"


def user_info_endpoint(uid: int) -> str:
    return f"api/user/info/{uid}"


def user_followings_endpoint() -> str:
    return "api/user/followings"


def user_followers_endpoint() -> str:
    return "api/user/followers"


def user_blacklist_endpoint() -> str:
    return "api/user/blacklist"


def problem_set_endpoint(problem_set_id: int) -> str:
    return f"/training/{problem_set_id}"


def contest_endpoint(contest_id: int) -> str:
    return f"contest/{contest_id}"


def discussion_endpoint(discussion_id: int) -> str:
    return f"discuss/{discussion_id}"


def team_endpoint(tid: int) -> str:
    return f"team/{tid}"


def team_members_endpoint(tid: int) -> str:
    return f"api/team/members/{tid}"


def team_problems_endpoint(tid: int) -> str:
    return f"api/team/problems/{tid}"


def team_problem_sets_endpoint(tid: int) -> str:
    return f"api/team/trainings/{tid}"


def team_contests_endpoint(tid: int) -> str:
    return f"api/team/contests/{tid}"


def paste_endpoint(paste_id: str) -> str:
    return f"paste/{paste_id}"


def record_endpoint(rid: str) -> str:
    return f"record/{rid}"


def article_endpoint(lid: str) -> str:
    return f"article/{lid}"


def image_endpoint(image_id: int) -> str:
    return f"/api/image/detail/{image_id}"


def list_params(page: int | None = None) -> ListRequestParams:
    return ListRequestParams(json={"page": page})


def problem_request_params(contest_id: int | None = None) -> ProblemRequestParams:
    return ProblemRequestParams(json={"contestId": contest_id})


def problem_list_params(
        page: int | None = None,
        order_by: str | None = None,
        order: Literal["asc", "desc"] | None = None,
        keyword: str | None = None,
        content: bool | None = None,
        problem_type: ProblemType | None = None,
        difficulty: int | None = None,
        tag: str | None = None,
) -> ProblemListRequestParams:
    return ProblemListRequestParams(json={
        "page": page,
        "orderBy": order_by,
        "order": order,
        "keyword": keyword,
        "content": content,
        "type": problem_type,
        "difficulty": difficulty,
        "tag": tag,
    })


def problem_set_list_params(
        page: int | None = None,
        keyword: str | None = None,
        problem_set_type: ProblemSetType | None = None,
) -> ProblemSetListRequestParams:
    return ProblemSetListRequestParams(json={
        "page": page,
        "keyword": keyword,
        "type": problem_set_type,
    })


def user_list_params(uid: int, page: int | None = None) -> UserListRequestParams:
    return UserListRequestParams(json={"user": uid, "page": page})


def contest_list_params(
        page: int | None = None,
        name: str | None = None,
        method: int | None = None,
        public: int | None = None,
) -> ContestListRequestParams:
    return ContestListRequestParams(json={
        "page": page,
        "name": name,
        "method": method,
        "public": public,
    })


def discussion_params(page: int | None = None, order_by: int | None = None) -> DiscussionRequestParams:
    return DiscussionRequestParams(json={"page": page, "orderBy": order_by})


def activity_params(uid: int, page: int | None = None) -> ActivityReuqestParams:
    return ActivityReuqestParams(json={"user": uid, "page": page})


def team_problem_list_params(
        page: int | None = None,
        keyword: str | None = None,
        order_by: Literal["pid", "name"] | None = None,
        order: Literal["asc", "desc"] | None = None,
) -> TeamProblemListRequestParams:
    return TeamProblemListRequestParams(json={
        "page": page,
        "keyword": keyword,
        "orderBy": order_by,
        "order": order,
    })


def transfer_problem_payload(target: TransferProblemType, is_clone: bool = False) -> dict[str, int | str]:
    if isinstance(target, int):
        data: dict[str, int | str] = {"type": "T", "teamID": target}
    else:
        data = {"type": target}

    if is_clone:
        data["operation"] = "clone"

    return data


def submit_code_payload(
        code: str,
        lang: int | None,
        enable_o2: bool | int,
        captcha: str,
) -> dict[str, str | int | bool | None]:
    return {
        "code": code,
        "lang": lang,
        "enableO2": enable_o2,
        "captcha": captcha,
    }
