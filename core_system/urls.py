from django.conf import settings 
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from complaints.views import ResolveTicketView
from accounts.views import DashboardSummaryView, MarkNotificationReadView, NotificationListView
from complaints.views import DispatcherAssignTicketView, DispatcherNewTicketsView, DispatcherUpdateTicketStatusView, SendTicketUpdateView, Tier1AssignTicketView,LiaisonInboxView, Tier1NewTicketsView ,DispatcherUpdateTicketStatusView, MergeTicketsView 



urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')), 
    path('api/dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('api/notifications/', NotificationListView.as_view(), name='notifications-list'),
    path('api/complaints/', include('complaints.urls')),
    path('api/notifications/mark-read/<int:pk>/', MarkNotificationReadView.as_view(), name='notifications-mark-read'),
    path('api/tickets/new', Tier1NewTicketsView.as_view(), name='tier1-new-tickets'),
    path('api/tickets/<str:ticket_id>/assign', Tier1AssignTicketView.as_view(), name='tier1-assign-ticket'),
    path('api/dispatcher/tickets/new', DispatcherNewTicketsView.as_view(), name='dispatcher-new-tickets'),
    path('api/liaison/tickets', LiaisonInboxView.as_view(), name='liaison-inbox'),
    path('api/dispatcher/tickets/<str:ticket_id>/status', DispatcherUpdateTicketStatusView.as_view(), name='dispatcher-update-status'),
    path('api/dispatcher/tickets/<str:ticket_id>/assign', DispatcherAssignTicketView.as_view(), name='dispatcher-assign-ticket'),
    path('api/tickets/<str:ticket_id>/updates', SendTicketUpdateView.as_view(), name='send-ticket-update'),
    path('api/tickets/merge', MergeTicketsView.as_view(), name='merge-tickets'),
    path('api/liaison/tickets/<str:ticket_id>/resolve', ResolveTicketView.as_view(), name='resolve-ticket'), 
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
