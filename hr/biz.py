"""人事薪資差勤服務：把各功能模組組成一個物件（畫面、手機 API、GPS 打卡網頁都透過它存取資料）。"""
from .attendance import AttMixin
from .core import Base, BizError, money, yuan  # noqa: F401
from .gl import GLMixin
from .laws import LawMixin
from .leave import LeaveMixin
from .occ import OccMixin
from .payroll import PayMixin
from .people import EmpMixin
from .reports import ReportsMixin


class Biz(Base, LawMixin, EmpMixin, AttMixin, LeaveMixin, OccMixin, PayMixin, GLMixin, ReportsMixin):
    pass
