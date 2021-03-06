# -*- coding: utf-8 -*-
# 版权所有 2019 深圳米筐科技有限公司（下称“米筐科技”）
#
# 除非遵守当前许可，否则不得使用本软件。
#
#     * 非商业用途（非商业用途指个人出于非商业目的使用本软件，或者高校、研究所等非营利机构出于教育、科研等目的使用本软件）：
#         遵守 Apache License 2.0（下称“Apache 2.0 许可”），您可以在以下位置获得 Apache 2.0 许可的副本：http://www.apache.org/licenses/LICENSE-2.0。
#         除非法律有要求或以书面形式达成协议，否则本软件分发时需保持当前许可“原样”不变，且不得附加任何条件。
#
#     * 商业用途（商业用途指个人出于任何商业目的使用本软件，或者法人或其他组织出于任何目的使用本软件）：
#         未经米筐科技授权，任何个人不得出于任何商业目的使用本软件（包括但不限于向第三方提供、销售、出租、出借、转让本软件、本软件的衍生产品、引用或借鉴了本软件功能或源代码的产品或服务），任何法人或其他组织不得出于任何目的使用本软件，否则米筐科技有权追究相应的知识产权侵权责任。
#         在此前提下，对本软件的使用同样需要遵守 Apache 2.0 许可，Apache 2.0 许可与本许可冲突之处，以本许可为准。
#         详细的授权流程，请联系 public@ricequant.com 获取。

from __future__ import division
import pprint
import re
import six
import collections
from decimal import getcontext, ROUND_FLOOR
from datetime import time

from contextlib import contextmanager
import numpy as np

from rqalpha.utils.exception import CustomError, CustomException
from rqalpha.const import EXC_TYPE, INSTRUMENT_TYPE, DEFAULT_ACCOUNT_TYPE, UNDERLYING_SYMBOL_PATTERN
from rqalpha.utils.datetime_func import TimeRange
from rqalpha.utils.i18n import gettext as _
from rqalpha.utils.py2 import lru_cache


class RqAttrDict(object):

    def __init__(self, d=None):
        self.__dict__ = d if d is not None else dict()

        for k, v in list(six.iteritems(self.__dict__)):
            if isinstance(v, dict):
                self.__dict__[k] = RqAttrDict(v)

    def __repr__(self):
        return pprint.pformat(self.__dict__)

    def __iter__(self):
        return self.__dict__.__iter__()

    def update(self, other):
        RqAttrDict._update_dict_recursive(self, other)

    def items(self):
        return six.iteritems(self.__dict__)

    iteritems = items

    def keys(self):
        return self.__dict__.keys()

    @staticmethod
    def _update_dict_recursive(target, other):
        if isinstance(other, RqAttrDict):
            other = other.__dict__
        if isinstance(target, RqAttrDict):
            target = target.__dict__

        for k, v in six.iteritems(other):
            if isinstance(v, collections.Mapping):
                r = RqAttrDict._update_dict_recursive(target.get(k, {}), v)
                target[k] = r
            else:
                target[k] = other[k]
        return target

    def convert_to_dict(self):
        result_dict = {}
        for k, v in list(six.iteritems(self.__dict__)):
            if isinstance(v, RqAttrDict):
                v = v.convert_to_dict()
            result_dict[k] = v
        return result_dict


def dummy_func(*args, **kwargs):
    return None


def id_gen(start=1):
    i = start
    while True:
        yield i
        i += 1


class Nop(object):
    def __init__(self):
        pass

    def nop(*args, **kw):
        pass

    def __getattr__(self, _):
        return self.nop


def to_sector_name(s):
    from rqalpha.model.instrument import SectorCode, SectorCodeItem

    for __, v in six.iteritems(SectorCode.__dict__):
        if isinstance(v, SectorCodeItem):
            if v.cn == s or v.en == s or v.name == s:
                return v.name
    # not found
    return s


def to_industry_code(s):
    from rqalpha.model.instrument import IndustryCode, IndustryCodeItem

    for __, v in six.iteritems(IndustryCode.__dict__):
        if isinstance(v, IndustryCodeItem):
            if v.name == s:
                return v.code
    return s


def create_custom_exception(exc_type, exc_val, exc_tb, strategy_filename):
    try:
        msg = str(exc_val)
    except:
        msg = ""

    error = CustomError()
    error.set_msg(msg)
    error.set_exc(exc_type, exc_val, exc_tb)

    import linecache

    filename = ''
    tb = exc_tb
    while tb:
        co = tb.tb_frame.f_code
        filename = co.co_filename
        if filename != strategy_filename:
            tb = tb.tb_next
            continue
        lineno = tb.tb_lineno
        func_name = co.co_name
        code = linecache.getline(filename, lineno).strip()
        error.add_stack_info(filename, lineno, func_name, code, tb.tb_frame.f_locals)
        tb = tb.tb_next

    if filename == strategy_filename:
        error.error_type = EXC_TYPE.USER_EXC

    user_exc = CustomException(error)
    return user_exc


def run_when_strategy_not_hold(func):
    from rqalpha.environment import Environment
    from rqalpha.utils.logger import system_log

    def wrapper(*args, **kwargs):
        if not Environment.get_instance().config.extra.is_hold:
            return func(*args, **kwargs)
        else:
            system_log.debug(_(u"not run {}({}, {}) because strategy is hold").format(func, args, kwargs))

    return wrapper


def merge_dicts(*dict_args):
    result = {}
    for d in dict_args:
        result.update(d)
    return result


INSTRUMENT_TYPE_STR_EHUM_MAP = {
    "CS": INSTRUMENT_TYPE.CS,
    "Future": INSTRUMENT_TYPE.FUTURE,
    "Option": INSTRUMENT_TYPE.OPTION,
    "ETF": INSTRUMENT_TYPE.ETF,
    "LOF": INSTRUMENT_TYPE.LOF,
    "INDX": INSTRUMENT_TYPE.INDX,
    "FenjiMu": INSTRUMENT_TYPE.FENJI_MU,
    "FenjiA": INSTRUMENT_TYPE.FENJI_A,
    "FenjiB": INSTRUMENT_TYPE.FENJI_B,
    'PublicFund': INSTRUMENT_TYPE.PUBLIC_FUND,
    "Bond": INSTRUMENT_TYPE.BOND,
    "Convertible": INSTRUMENT_TYPE.CONVERTIBLE,
    "Spot": INSTRUMENT_TYPE.SPOT,
    "Repo": INSTRUMENT_TYPE.REPO
}


def instrument_type_str2enum(type_str):
    try:
        return INSTRUMENT_TYPE_STR_EHUM_MAP[type_str]
    except KeyError:
        raise NotImplementedError


def account_type_str2enum(type_str):
    return {
        DEFAULT_ACCOUNT_TYPE.STOCK.name: DEFAULT_ACCOUNT_TYPE.STOCK,
        DEFAULT_ACCOUNT_TYPE.FUTURE.name: DEFAULT_ACCOUNT_TYPE.FUTURE,
        DEFAULT_ACCOUNT_TYPE.BOND.name: DEFAULT_ACCOUNT_TYPE.BOND,
    }[type_str]


INST_TYPE_IN_STOCK_ACCOUNT = [
    INSTRUMENT_TYPE.CS,
    INSTRUMENT_TYPE.ETF,
    INSTRUMENT_TYPE.LOF,
    INSTRUMENT_TYPE.INDX,
    INSTRUMENT_TYPE.FENJI_MU,
    INSTRUMENT_TYPE.FENJI_A,
    INSTRUMENT_TYPE.FENJI_B,
    INSTRUMENT_TYPE.PUBLIC_FUND
]


@lru_cache(None)
def get_account_type_enum(order_book_id):
    from rqalpha.environment import Environment
    instrument = Environment.get_instance().get_instrument(order_book_id)
    enum_type = instrument.enum_type
    if enum_type in INST_TYPE_IN_STOCK_ACCOUNT:
        return DEFAULT_ACCOUNT_TYPE.STOCK
    elif enum_type == INSTRUMENT_TYPE.FUTURE:
        return DEFAULT_ACCOUNT_TYPE.FUTURE
    elif enum_type == INSTRUMENT_TYPE.BOND:
        return DEFAULT_ACCOUNT_TYPE.BOND
    else:
        raise NotImplementedError


def get_account_type(order_book_id):
    return get_account_type_enum(order_book_id).name


def get_upper_underlying_symbol(order_book_id):
    p = re.compile(UNDERLYING_SYMBOL_PATTERN)
    result = p.findall(order_book_id)
    return result[0] if len(result) == 1 else None


def is_night_trading(universe):
    # for compatible
    from rqalpha.environment import Environment
    return Environment.get_instance().data_proxy.is_night_trading(universe)


def merge_trading_period(trading_period):
    result = []
    for time_range in sorted(set(trading_period)):
        if result and result[-1].end >= time_range.start:
            result[-1] = TimeRange(start=result[-1].start, end=max(result[-1].end, time_range.end))
        else:
            result.append(time_range)
    return result


STOCK_TRADING_PERIOD = [
    TimeRange(start=time(9, 31), end=time(11, 30)),
    TimeRange(start=time(13, 1), end=time(15, 0)),
]


def get_trading_period(universe, accounts):
    # for compatible
    from rqalpha.environment import Environment
    trading_period = STOCK_TRADING_PERIOD if DEFAULT_ACCOUNT_TYPE.STOCK.name in accounts else []
    return Environment.get_instance().data_proxy.get_trading_period(universe, trading_period)


def is_trading(dt, trading_period):
    t = dt.time()
    for time_range in trading_period:
        if time_range.start <= t <= time_range.end:
            return True
    return False


@contextmanager
def run_with_user_log_disabled(disabled=True):
    from rqalpha.utils.logger import user_log

    if disabled:
        user_log.disable()
    try:
        yield
    finally:
        if disabled:
            user_log.enable()


def unwrapper(func):
    f2 = func
    while True:
        f = f2
        f2 = getattr(f2, "__wrapped__", None)
        if f2 is None:
            break
    return f


def is_run_from_ipython():
    try:
        __IPYTHON__
        return True
    except NameError:
        return False


def is_valid_price(price):
    return not (price is None or np.isnan(price) or price <= 0)


@contextmanager
def decimal_rounding_floor():
    original_rounding_option = getcontext().rounding
    getcontext().rounding = ROUND_FLOOR
    yield
    getcontext().rounding = original_rounding_option
