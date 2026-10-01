"""Execute the pinned upstream models/routes with narrow session/auth dependencies.

The dependencies are replaced with an in-memory database and pre-authenticated
synthetic principals. Authentication/JWT and frontend flows are NOT under test.
"""
import contextlib
import importlib.util
import io
import sys
import types
import uuid
from typing import Annotated


def run_application(payload):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    for name in ("app", "app.api", "app.api.deps"):
        package = types.ModuleType(name)
        package.__path__ = []
        sys.modules[name] = package
    model_spec = importlib.util.spec_from_file_location("app.models", "/task/models.py")
    models = importlib.util.module_from_spec(model_spec)
    sys.modules["app.models"] = models
    model_spec.loader.exec_module(models)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    identity = {name: uuid.UUID(int=index) for index, name in enumerate(("owner", "other", "admin", "outsider"), 1)}
    users = {
        name: models.User(id=identifier, email=f"{name}@example.org", hashed_password="synthetic-not-a-login",
                          is_superuser=(name == "admin"))
        for name, identifier in identity.items()
    }
    actors = {"current": users["owner"]}

    def get_session():
        with Session(engine) as session:
            yield session

    def get_user():
        return actors["current"]

    deps = sys.modules["app.api.deps"]
    deps.SessionDep = Annotated[Session, Depends(get_session)]
    deps.CurrentUser = Annotated[models.User, Depends(get_user)]
    route_spec = importlib.util.spec_from_file_location("candidate_routes", "/task/target.py")
    routes = importlib.util.module_from_spec(route_spec)
    with contextlib.redirect_stdout(io.StringIO()):
        route_spec.loader.exec_module(routes)
    application = FastAPI()
    application.include_router(routes.router)
    client = TestClient(application, raise_server_exceptions=False)
    owner_names = {str(identifier): name for name, identifier in identity.items()}
    observations = []
    for case in payload["cases"]:
        # Reset the database per case so one operation cannot alter another case.
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all([
                models.User(id=identifier, email=f"{name}@example.org", hashed_password="synthetic-not-a-login",
                            is_superuser=(name == "admin"))
                for name, identifier in identity.items()
            ])
            session.commit()
            for index, name in enumerate(("owner", "other"), 100):
                session.add(models.Item(id=uuid.UUID(int=index), title=f"{name}-item", owner_id=identity[name]))
            session.commit()
        actors["current"] = users[case["actor"]]
        target_id = {"owned": 100, "other": 101, "missing": 999}.get(case.get("target"), 100)
        target_url = f"/items/{uuid.UUID(int=target_id)}"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                operation = case["operation"]
                if operation == "list":
                    response = client.get("/items/", params={"skip": case.get("skip", 0)})
                elif operation == "create":
                    response = client.post("/items/", json={"title": "new-item", "owner_id": str(identity["other"])})
                elif operation == "update":
                    response = client.put(target_url, json={"title": "updated"})
                elif operation == "delete":
                    response = client.delete(target_url)
                else:
                    response = client.get(target_url)
            value = {"status": response.status_code}
            if response.status_code == 200:
                body = response.json()
                if "owner_id" in body:
                    value["owner"] = owner_names.get(body["owner_id"], "unknown")
                if "data" in body:
                    value["owners"] = sorted(owner_names.get(row["owner_id"], "unknown") for row in body["data"])
                    value["count"] = body["count"]
            observations.append({"id": case["id"], "value": value})
        except Exception as error:
            observations.append({"id": case["id"], "error": type(error).__name__ + ": " + str(error)[:300]})
    return observations
