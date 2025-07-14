from django.urls import path, include
from . import views

urlpatterns = [
    # User endpoints
    path('users/create/', views.create_or_get_user, name='create-user'),
    path('users/<int:telegram_id>/language/', views.update_user_language, name='update-language'),
    path('users/<int:telegram_id>/properties/', views.user_properties, name='user-properties'),
    path('users/<int:telegram_id>/favorites/', views.user_favorites, name='user-favorites'),
    
    # Property endpoints
    path('properties/', views.PropertyListCreateAPIView.as_view(), name='properties-list'),
    path('properties/<int:pk>/', views.PropertyDetailAPIView.as_view(), name='property-detail'),
    path('properties/by-location/', views.properties_by_location, name='properties-by-location'),
    
    # Location endpoints
    path('regions/', views.regions_list, name='regions-list'),
    path('districts/', views.districts_list, name='districts-list'),
    path('districts/<int:region_id>/', views.districts_list, name='districts-by-region'),
    path('districts/region/<str:region_key>/', views.districts_by_region_key, name='districts-by-region-key'),
    
    # Favorites endpoints
    path('favorites/add/', views.add_to_favorites, name='add-favorite'),
    path('favorites/remove/<int:telegram_id>/<int:property_id>/', 
         views.remove_from_favorites, name='remove-favorite'),
    
    # Statistics
    path('statistics/', views.property_statistics, name='statistics'),
]