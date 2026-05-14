from django.urls import path

from apps.schedule.views import (
    ScheduleConfigView,
    ScheduleHistoryView,
    ScheduleLiveLogView,
    ScheduleLogFileView,
    ScheduleStartView,
    ScheduleStopView,
)

urlpatterns = [
    path("schedule/<str:command>/",             ScheduleConfigView.as_view(),    name="schedule-config"),
    path("schedule/<str:command>/start/",       ScheduleStartView.as_view(),     name="schedule-start"),
    path("schedule/<str:command>/stop/",        ScheduleStopView.as_view(),      name="schedule-stop"),
    path("schedule/<str:command>/live-log/",    ScheduleLiveLogView.as_view(),   name="schedule-live-log"),
    path("schedule/<str:command>/history/",     ScheduleHistoryView.as_view(),   name="schedule-history"),
    path("schedule/<str:command>/log-file/",    ScheduleLogFileView.as_view(),   name="schedule-log-file"),
]
