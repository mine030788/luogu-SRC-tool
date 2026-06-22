__all__ = [
    "make_list",
    "JsonSerializable",
    "Printable",
    "CacheItem",
    "CachePool",
]

from types import UnionType
from typing import Generic, TypeVar, Dict, Any, Callable, Literal, Union, get_args, get_origin

import json
import time

from .strings import str_type_of, str_val, decorating, str_type


_NONE_TYPE = type(None)


def make_list(val) -> list:
    if isinstance(val, list):
        return list(val)
    else:
        return [val]


def _is_union_type(expected_type: Any) -> bool:
    return get_origin(expected_type) in (Union, UnionType)


def _is_literal_type(expected_type: Any) -> bool:
    return get_origin(expected_type) is Literal


def _conversion_error(key: str | None, expected_type: Any, value: Any) -> TypeError:
    return TypeError(f"{key} Expected {expected_type}, got {type(value)} with value {value}")


def _parse_union_type(key: str | None, value: Any, expected_type: Any) -> Any:
    errors = []
    for candidate in get_args(expected_type):
        if candidate is _NONE_TYPE:
            if value is None:
                return None
            continue
        try:
            return _parse_typed_value(key, value, candidate)
        except (TypeError, ValueError) as e:
            errors.append(e)
    raise _conversion_error(key, expected_type, value) from (errors[-1] if errors else None)


def _parse_literal_type(key: str | None, value: Any, expected_type: Any) -> Any:
    choices = get_args(expected_type)
    if value not in choices:
        raise _conversion_error(key, expected_type, value)
    return value


def _parse_list_type(key: str | None, value: Any, expected_type: Any) -> list[Any]:
    origin = get_origin(expected_type)
    item_types = list(get_args(expected_type)) if origin is list else expected_type
    if len(item_types) != 1:
        raise TypeError(f"List type must have exactly one element type: {expected_type}")
    item_type = item_types[0]
    if not isinstance(value, list):
        raise TypeError(f"{key} Expected a list of {item_type}, got {type(value)}")
    return [_parse_typed_value(None, item, item_type) for item in value]


def _parse_tuple_type(key: str | None, value: Any, expected_type: Any) -> tuple[Any, ...]:
    origin = get_origin(expected_type)
    item_types = get_args(expected_type) if origin is tuple else expected_type
    if not isinstance(value, (list, tuple)) or len(value) != len(item_types):
        raise TypeError(f"{key} Expected a tuple of {item_types}, got {type(value)} with value {value}")
    return tuple(_parse_typed_value(None, item, item_type) for item, item_type in zip(value, item_types))


def _parse_dict_type(key: str | None, value: Any, expected_type: Any) -> dict[Any, Any]:
    origin = get_origin(expected_type)
    if origin is dict:
        key_type, value_type = get_args(expected_type)
    else:
        key_type, value_type = list(expected_type.items())[0]
    if not isinstance(value, (dict, list)):
        raise TypeError(f"{key} Expected a dict of {expected_type}, got {type(value)}")
    if isinstance(value, list):
        return {
            _parse_typed_value(None, key_type(index), key_type): _parse_typed_value(None, item, value_type)
            for index, item in enumerate(value)
        }
    return {
        _parse_typed_value(None, item_key, key_type): _parse_typed_value(None, item_value, value_type)
        for item_key, item_value in value.items()
    }


def _parse_typed_value(key: str | None, value: Any, expected_type: Any) -> Any:
    if expected_type is Any:
        return value
    if value is None:
        return None

    origin = get_origin(expected_type)
    if _is_union_type(expected_type):
        return _parse_union_type(key, value, expected_type)
    if _is_literal_type(expected_type):
        return _parse_literal_type(key, value, expected_type)
    if isinstance(expected_type, list) or origin is list:
        return _parse_list_type(key, value, expected_type)
    if isinstance(expected_type, tuple) or origin is tuple:
        return _parse_tuple_type(key, value, expected_type)
    if isinstance(expected_type, dict) or origin is dict:
        return _parse_dict_type(key, value, expected_type)
    if isinstance(expected_type, type) and issubclass(expected_type, JsonSerializable):
        return expected_type(json=value)
    if isinstance(expected_type, type) and not isinstance(value, expected_type):
        raise TypeError(f"{key} Expected {expected_type}, got {type(value)}")
    return value


class JsonSerializable:
    __type_dict__ = {}  # 子类应定义属性名与类型的映射

    def __init__(self, json=None):
        if json is None:
            json = {}
        self.parse(json)

    def parse(self, json):
        """
        初始化对象，将 JSON 数据映射到对象属性
        """
        if not isinstance(json, dict):
            raise TypeError(f"Expected a dictionary, got {type(json)}")

        for key, value in json.items():
            expected_type = self.__type_dict__.get(key)

            if expected_type is None:
                continue

            if value is not None:
                value = _parse_typed_value(key, value, expected_type)

            setattr(self, key, value)

        for key, expected_type in self.__type_dict__.items():
            if not hasattr(self, key):
                setattr(self, key, None)  # 默认值为 None

    def to_json(self):
        """
        转换对象为 JSON 格式（字典）
        """

        def serialize(_value):
            if isinstance(_value, JsonSerializable):
                return _value.to_json()  # 递归处理嵌套对象
            elif isinstance(_value, list):
                return [serialize(v) for v in _value]  # 递归处理列表
            elif isinstance(_value, tuple):
                return [serialize(v) for v in _value]  # 元组转换为列表
            elif isinstance(_value, dict):
                return {serialize(k): serialize(v) for k, v in _value.items()}  # 递归处理字典
            else:
                return _value

        json_data = {}
        for key, value in self.__type_dict__.items():
            attr_value = getattr(self, key, None)
            if attr_value is None:
                continue
            json_data[key] = serialize(attr_value)

        return json_data

    @classmethod
    def from_file(cls, path: str):
        with open(path, 'r') as json_file:
            data = json.load(json_file)

        return cls(json=data)

    def store(self, path: str):
        with open(path, 'w') as json_file:
            json_file.write(json.dumps(self.to_json()))


class Printable:
    __type_dict__ = {}

    def __tree__(self, offset=""):
        s = ""
        for x, y in self.__dict__.items():
            tail = "├─ " if x != list(self.__dict__.keys())[-1] else "└─ "
            addi = "│  " if x != list(self.__dict__.keys())[-1] else "   "
            if y is None:
                s += offset + tail + f"{str_type(self.__type_dict__[x])} {x}: {decorating('None', 31)}\n"
            elif isinstance(y, list):
                s += offset + tail + f"{str_type_of(y)} {x}:\n"
                new_offset = offset + addi
                for p in range(len(y)):
                    tail = "├─ " if p != len(y) - 1 else "└─ "
                    addi = "│  " if p != len(y) - 1 else "   "
                    if isinstance(y[p], Printable):
                        s += new_offset + tail + f"{x}[{p}] -> {str_type_of(y[p])} :\n" + y[p].__tree__(
                            new_offset + addi)
                    else:
                        s += new_offset + tail + f"{x}[{p}] -> {str_type_of(y[p])} : {str_val(y[p])}\n"
            elif isinstance(y, dict):
                s += offset + tail + f"{str_type_of(y)} {x}:\n"
                new_offset = offset + addi
                for p, (k, v) in enumerate(y.items()):
                    tail = "├─ " if p != len(y) - 1 else "└─ "
                    addi = "│  " if p != len(y) - 1 else "   "
                    if isinstance(v, Printable):
                        s += new_offset + tail + f"{x}[{str_val(k)}] -> {str_type_of(v)} :\n" + v.__tree__(new_offset + addi)
                    else:
                        s += new_offset + tail + f"{x}[{str_val(k)}] -> {str_type_of(v)} : {str_val(v)}\n"
            elif isinstance(y, Printable):
                s += offset + tail + f"{str_type_of(y)} {x} :\n" + y.__tree__(offset + addi)
            else:
                s += offset + tail + f"{str_type_of(y)} {x} : {str_val(y)}\n"
        return s

    def __str__(self):
        return decorating(str_type_of(self) + "\n" + self.__tree__(), 37, 0)

_T = TypeVar("_T")
LoadFunctionType = Callable[[str], _T]

class CacheItem(Generic[_T]):
    def __init__(self, 
            id: str, 
            value: _T | None, 
            cache_duration: float, 
            load_function: LoadFunctionType | None = None
    ):
        self.id: str = id
        self.value: _T | None = value
        self.type: type = type(value)
        self.cache_duration: float = cache_duration
        self.last_loaded_time: float = time.time()
        self.load_function: LoadFunctionType | None = load_function
    
    def refresh( self,
            new_value: _T | None = None,
            new_cache_duration: float | None = None,
            new_load_function: LoadFunctionType[_T] | None = None
    ):
        self.value = new_value or self.value
        self.load_function = new_load_function or self.load_function
        load_function = self.load_function
        if new_value is None and load_function is None:
            raise ValueError("No new value load function provided")
        if new_value is None:
            assert load_function is not None
            self.value = load_function(self.id)
        self.cache_duration = new_cache_duration or self.cache_duration
        self.last_loaded_time = time.time()
    
    def check_expired(self) -> bool:
        if time.time() - self.last_loaded_time > self.cache_duration:
            return True
        return False

    def _state(self):
        if self.check_expired():
            return decorating("Expired", "31")
        else:
            return decorating(f"Valid<{self.last_loaded_time + self.cache_duration - time.time()}>", "32")
    
    def __repr__(self):
        return f"CacheItem<{self.type.__name__}, id={self.id}, {self._state()}> : {self.value}"

class CachePool(Generic[_T]):
    def __init__(self, 
            default_cache_duration: int = 60, 
            default_load_function: LoadFunctionType | None = None
    ):
        self._cache: Dict[str, CacheItem[_T]] = {}
        self._default_cache_duration: int = default_cache_duration
        self._default_load_function: LoadFunctionType | None = default_load_function

    def try_refresh(self, resource_id: str) -> bool:
        item = self._cache.get(resource_id)
        if item is None:
            return False
        try:
            item.refresh()
            return True
        except ValueError:
            self._cache.pop(resource_id)
            return False

    def check_expired(self, resource_id: str) -> bool:
        item = self._cache.get(resource_id)
        if item is None:
            return True
        if item.check_expired():
            return not self.try_refresh(resource_id)
        return False

    def load(self, resource_id: str) -> _T | None:
        if self._cache.get(resource_id) is None:
            if self._default_load_function is None:
                return None
            self.store(resource_id, None)
        if self.check_expired(resource_id):
            return None
        return self._cache[resource_id].value
    
    async def async_load(self, resource_id: str) -> _T | None:
        return self.load(resource_id)

    def store(self, 
            resource_id: str, 
            value: _T | None, 
            cache_duration: int | None = None, 
            load_function: LoadFunctionType | None = None
    ) -> CacheItem[_T]:
        if cache_duration is None:
            cache_duration = self._default_cache_duration
        if load_function is None:
            load_function = self._default_load_function
        if value is None and load_function is None:
            raise ValueError("No new value load function provided")
        if value is None:
            assert load_function is not None
            value = load_function(resource_id)
        self._cache[resource_id] = CacheItem(resource_id, value, cache_duration, load_function)
        return self._cache[resource_id]

    def clear(self):
        self._cache.clear()

class LazyType:
    def __init__(self, load_function: Callable[[], Any], cache_duration=60):
        self._load_function = load_function
        self._loaded = False
        self._data = None
        self._cache_duration = cache_duration
        self._last_loaded_time: float | None = None

    def _load(self):
        if (
                not self._loaded
                or self._last_loaded_time is None
                or (
                    self._cache_duration
                    and (time.time() - self._last_loaded_time) > self._cache_duration
                )
        ):
            self._data = self._load_function()
            self._loaded = True
            self._last_loaded_time = time.time()

    def __getattr__(self, name):
        self._load()
        return getattr(self._data, name)

    def __setattr__(self, name, value):
        if name in ("_load_function", "_loaded", "_data", "_cache_duration", "_last_loaded_time"):
            super().__setattr__(name, value)
        else:
            self._load()
            setattr(self._data, name, value)

    def __repr__(self):
        self._load()
        return repr(self._data)

class LazyProxy:
    def __init__(self, load_function: Callable[[], Any], cache_duration=60):
        self._lazy = LazyType(load_function, cache_duration)

    def __getattr__(self, name):
        return getattr(self._lazy, name)

    def __setattr__(self, name, value):
        if name == "_lazy":
            super().__setattr__(name, value)
        else:
            setattr(self._lazy, name, value)
