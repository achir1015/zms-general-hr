import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hr.database import DB  # noqa: E402
from hr.dbserver import LocalDatabaseServer  # noqa: E402
from hr.settings import Settings, find_mariadb  # noqa: E402

TEST_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_db")


@pytest.fixture(scope="session")
def server():
    os.environ["HR_DATA_DIR"] = TEST_ROOT
    st = Settings(port=3388, password="test-pw-123", database="hr_test", mariadb_bin=find_mariadb(),
                  datadir=os.path.join(TEST_ROOT, "mariadb"))
    srv = LocalDatabaseServer(st)
    srv.start()
    yield st
    srv.stop()


@pytest.fixture()
def db(server):
    d = DB(server)
    c = d.connect(use_db=False)
    with c.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS hr_test")
    c.close()
    d.prepare()
    yield d
    d.close()


@pytest.fixture()
def biz(db):
    from hr.biz import Biz
    b = Biz(db)
    b.create_first_admin("admin", "管理員", "admin123")
    b.login("admin", "admin123")
    return b
