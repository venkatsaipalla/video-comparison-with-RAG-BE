from app.models import EngagementMetrics


def compute_engagement(
    views: int | None,
    likes: int | None,
    comments: int | None,
) -> EngagementMetrics:
    like_rate = None
    comment_rate = None
    engagement_rate = None

    if views and views > 0:
        if likes is not None:
            like_rate = round(likes / views, 6)
        if comments is not None:
            comment_rate = round(comments / views, 6)
        if likes is not None and comments is not None:
            engagement_rate = round((likes + comments) / views, 6)

    return EngagementMetrics(
        views=views,
        likes=likes,
        comments=comments,
        like_rate=like_rate,
        comment_rate=comment_rate,
        engagement_rate=engagement_rate,
    )
