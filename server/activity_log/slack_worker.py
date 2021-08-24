import time
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests

from .. import config
from ..models import ActivityLogRecord
from ..auth.lib import UserType
from ..database import db_session
from . import activity_log
from ..sentry import configure_sentry


# pylint: disable=too-many-return-statements
def slack_message(activity: activity_log.Activity):
    base = activity.base
    org_link = urljoin(config.HTTP_ORIGIN, f"/support/orgs/{base.organization_id}")
    org_context = dict(
        type="mrkdwn", text=f":flag-us: <{org_link}|{base.organization_name}>",
    )
    user_type = (
        {
            UserType.AUDIT_ADMIN: "Audit admin",
            UserType.JURISDICTION_ADMIN: "Jurisdiction admin"
        }[UserType(base.user_type)]
        if base.user_type
        else ""
    )
    user_name = ( base.user_key )
    user_context = dict(
        type="mrkdwn",
        text=(
            f":technologist: Support user {base.support_user_email} logged in as {user_type.lower()} {user_name}"
            if base.support_user_email
            else f":technologist: {user_type} {user_name}"
        ),
    )
    time_context = dict(
        type="mrkdwn",
        text=f":clock3: <!date^{int(activity.timestamp.timestamp())}^{{date_short}}, {{time_secs}}|{activity.timestamp.isoformat()}>",
    )
    election_context = dict(
        type="mrkdwn",
        text=f":microscope: <{base.election_name}>",
    )

    if isinstance(activity, activity_log.JurisdictionActivity):
        jurisdiction_link = urljoin(
            config.HTTP_ORIGIN, f"/support/orgs/{activity.jurisdiction_id}"
        )
        jurisdiction_context = dict(
            type="mrkdwn",
            text=f":classical_building: <{jurisdiction_link}|{activity.jurisdiction_name}> ",
        )

    acting_user = base.support_user_email or base.user_key

    if isinstance(activity, activity_log.CreateElection):
        return dict(
            text=f"{acting_user} created an election: {base.election_name}",
            blocks=[
                dict(
                    type="section",
                    text=dict(
                        type="mrkdwn",
                        text=f"*{acting_user} created an election: <{base.election_name}>",
                    ),
                ),
                dict(
                    type="context", elements=[org_context, time_context, user_context],
                ),
            ],
        )

    if isinstance(activity, activity_log.DeleteElection):
        return dict(
            text=f"{acting_user} deleted an election: {base.election_name}",
            blocks=[
                dict(
                    type="section",
                    text=dict(
                        type="mrkdwn",
                        text=f"*{acting_user} deleted an election: <{base.election_name}>",
                    ),
                ),
                dict(
                    type="context", elements=[org_context, time_context, user_context],
                ),
            ],
        )

    if isinstance(activity, activity_log.RecordResults):
        return dict(
            text=f"Results recorded for {activity.jurisdiction_name}",
            blocks=[
                dict(
                    type="section",
                    text=dict(
                        type="mrkdwn",
                        text=f"*Results recorded for {activity.jurisdiction_name}*",
                    ),
                ),
                dict(
                    type="context",
                    elements=[
                        org_context,
                        jurisdiction_context,
                        election_context,
                        time_context,
                        user_context,
                    ],
                ),
            ],
        )

    raise Exception(  # pragma: no cover
        f"slack_message not implemented for activity type: {activity.__class__.__name__}"
    )


# The optional organization_id parameter makes this function thread-safe for
# testing. Each test has its own org, and we don't want tests running in
# parallel to influence each other.
def send_new_slack_notification(organization_id: str = None) -> None:
    if config.SLACK_WEBHOOK_URL is None:
        raise Exception("Missing SLACK_WEBHOOK_URL")

    record = (
        ActivityLogRecord.query.filter(ActivityLogRecord.posted_to_slack_at.is_(None))
        .filter_by(**dict(organization_id=organization_id) if organization_id else {})
        .order_by(ActivityLogRecord.timestamp)
        .limit(1)
        .one_or_none()
    )
    if record:
        ActivityClass = getattr(  # pylint: disable=invalid-name
            activity_log, record.activity_name
        )
        activity: activity_log.Activity = ActivityClass(
            **dict(
                record.info,
                base=activity_log.ActivityBase(**record.info["base"]),
                timestamp=record.timestamp,
            )
        )

        rv = requests.post(config.SLACK_WEBHOOK_URL, json=slack_message(activity))
        if rv.status_code != 200:
            raise Exception(f"Error posting record {record.id}:\n\n{rv.text}")

        record.posted_to_slack_at = datetime.now(timezone.utc)


if __name__ == "__main__":  # pragma: no cover
    configure_sentry()
    # We send at most one Slack notification per second, since that's what the
    # Slack API allows.
    while True:
        send_new_slack_notification()
        # We always commit the current transaction before sleeping, otherwise
        # we will have "idle in transaction" queries that will lock the
        # database, which gets in the way of migrations.
        db_session.commit()
        time.sleep(1)