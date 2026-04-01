from __future__ import annotations

from django.http import HttpRequest

from app.models_django import AdminAccount, Client, Designer


CUSTOMER_ID_SESSION_KEY = "customer_id"
CUSTOMER_NAME_SESSION_KEY = "customer_name"
ADMIN_ID_SESSION_KEY = "admin_id"
ADMIN_NAME_SESSION_KEY = "admin_name"
DESIGNER_ID_SESSION_KEY = "designer_id"
DESIGNER_NAME_SESSION_KEY = "designer_name"
OWNER_DASHBOARD_ALLOWED_SESSION_KEY = "owner_dashboard_allowed"


def set_customer_session(*, request: HttpRequest, client: Client) -> None:
    request.session[CUSTOMER_ID_SESSION_KEY] = client.id
    request.session[CUSTOMER_NAME_SESSION_KEY] = client.name
    request.session.modified = True


def clear_customer_session(*, request: HttpRequest) -> None:
    request.session.pop(CUSTOMER_ID_SESSION_KEY, None)
    request.session.pop(CUSTOMER_NAME_SESSION_KEY, None)
    request.session.modified = True


def get_session_customer(*, request: HttpRequest) -> Client | None:
    client_id = request.session.get(CUSTOMER_ID_SESSION_KEY)
    if not client_id:
        return None
    return Client.objects.filter(id=client_id).first()


def set_admin_session(*, request: HttpRequest, admin: AdminAccount) -> None:
    request.session[ADMIN_ID_SESSION_KEY] = admin.id
    request.session[ADMIN_NAME_SESSION_KEY] = admin.name
    request.session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
    request.session.modified = True


def clear_admin_session(*, request: HttpRequest) -> None:
    request.session.pop(ADMIN_ID_SESSION_KEY, None)
    request.session.pop(ADMIN_NAME_SESSION_KEY, None)
    request.session.pop(OWNER_DASHBOARD_ALLOWED_SESSION_KEY, None)
    request.session.modified = True


def get_session_admin(*, request: HttpRequest) -> AdminAccount | None:
    admin_id = request.session.get(ADMIN_ID_SESSION_KEY)
    if not admin_id:
        return None
    return AdminAccount.objects.filter(id=admin_id, is_active=True).first()


def set_designer_session(*, request: HttpRequest, designer: Designer) -> None:
    request.session[DESIGNER_ID_SESSION_KEY] = designer.id
    request.session[DESIGNER_NAME_SESSION_KEY] = designer.name
    request.session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
    request.session.modified = True


def clear_designer_session(*, request: HttpRequest) -> None:
    request.session.pop(DESIGNER_ID_SESSION_KEY, None)
    request.session.pop(DESIGNER_NAME_SESSION_KEY, None)
    request.session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
    request.session.modified = True


def get_session_designer(*, request: HttpRequest) -> Designer | None:
    designer_id = request.session.get(DESIGNER_ID_SESSION_KEY)
    if not designer_id:
        return None
    return Designer.objects.select_related("shop").filter(id=designer_id, is_active=True).first()


def allow_owner_dashboard(*, request: HttpRequest) -> None:
    request.session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = True
    request.session.modified = True


def revoke_owner_dashboard(*, request: HttpRequest) -> None:
    request.session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
    request.session.modified = True


def can_access_owner_dashboard(*, request: HttpRequest) -> bool:
    return bool(request.session.get(OWNER_DASHBOARD_ALLOWED_SESSION_KEY))
