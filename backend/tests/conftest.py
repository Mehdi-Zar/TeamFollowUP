import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Squad, Tribe, User
from app.security import hash_password

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded(db):
    t1 = Tribe(name="Tribe One", display_order=1)
    t2 = Tribe(name="Tribe Two", display_order=2)
    db.add_all([t1, t2])
    db.flush()

    admin = User(email="admin@test", display_name="Admin", role="admin",
                 is_break_glass=True, password_hash=hash_password("pw"))
    tribe = User(email="tribe@test", display_name="Tribe", role="tribe_leader", tribe_id=t1.id, password_hash=hash_password("pw"))
    tribe2 = User(email="tribe2@test", display_name="Tribe2", role="tribe_leader", tribe_id=t2.id, password_hash=hash_password("pw"))
    sl_a = User(email="sl_a@test", display_name="SL A", role="squad_leader", tribe_id=t1.id, password_hash=hash_password("pw"))
    sl_b = User(email="sl_b@test", display_name="SL B", role="squad_leader", tribe_id=t1.id, password_hash=hash_password("pw"))
    member = User(email="member@test", display_name="Member", role="member", tribe_id=t1.id, password_hash=hash_password("pw"))
    db.add_all([admin, tribe, tribe2, sl_a, sl_b, member])
    db.flush()

    squad_a = Squad(name="Squad A", tribe_id=t1.id, leader_user_id=sl_a.id, display_order=1)
    squad_b = Squad(name="Squad B", tribe_id=t1.id, leader_user_id=sl_b.id, display_order=2)
    squad_c = Squad(name="Squad C", tribe_id=t2.id, display_order=3)  # other tribe
    db.add_all([squad_a, squad_b, squad_c])
    db.commit()
    return {
        "admin": admin.email, "tribe": tribe.email, "tribe2": tribe2.email,
        "sl_a": sl_a.email, "sl_b": sl_b.email, "member": member.email,
        "squad_a": squad_a.id, "squad_b": squad_b.id, "squad_c": squad_c.id,
        "t1": t1.id, "t2": t2.id,
        # user ids (for endpoints that take an owner/user id, not an email)
        "sl_a_id": sl_a.id, "sl_b_id": sl_b.id, "member_id": member.id,
    }


@pytest.fixture()
def client():
    return TestClient(app)


def login(client: TestClient, email: str, password: str = "pw") -> TestClient:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return client
