from django.urls import path
from .views import ComplaintDetailView, ComplaintListView, CreateComplaintView, EvaluateComplaintView, ToggleUpvoteComplaintView, VerifyComplaintView

urlpatterns = [
    path('create/', CreateComplaintView.as_view(), name='create-complaint'),
    path('', ComplaintListView.as_view(), name='complaints-list'),
    path('verify/<str:ticket_number>/', VerifyComplaintView.as_view(), name='verify-complaint'),
    path('<str:ticket_number>/upvote/', ToggleUpvoteComplaintView.as_view(), name='upvote-complaint'),
    path('<str:ticket_number>/evaluate/', EvaluateComplaintView.as_view(), name='evaluate-complaint'),
    path('<str:ticket_number>/', ComplaintDetailView.as_view(), name='complaint-detail'),
]