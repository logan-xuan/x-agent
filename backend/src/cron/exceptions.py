"""Custom exceptions for cron module."""


class CronError(Exception):
    """Base exception for cron module."""

    pass


class SchedulerError(CronError):
    """Scheduler operation error."""

    pass


class JobNotFoundError(CronError):
    """Job not found error."""

    pass


class ScheduleNotFoundError(CronError):
    """Schedule not found error."""

    pass


class TaskNotFoundError(CronError):
    """Task not found error."""

    pass


class InvalidTriggerError(CronError):
    """Invalid trigger configuration error."""

    pass


class JobExecutionError(CronError):
    """Job execution error."""

    pass
