from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("members", views.MemberViewSet, basename="member")
router.register("invitations", views.InvitationViewSet, basename="invitation")

urlpatterns = [
    path("workspaces/", views.WorkspaceListView.as_view(), name="workspace-list"),
    path("workspaces/switch/", views.SwitchWorkspaceView.as_view(), name="workspace-switch"),
    path("business/", views.CurrentBusinessView.as_view(), name="business-current"),
    path("invitations/preview/", views.InvitationPreviewView.as_view(), name="invitation-preview"),
    path("invitations/accept/", views.InvitationAcceptView.as_view(), name="invitation-accept"),
    *router.urls,
]
