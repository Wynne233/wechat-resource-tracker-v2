from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .models import Resource, ResourceScore
from .utils import new_id


STATUS_SCORE = {
    "available": 100,
    "review": 65,
    "suspected_down": 35,
    "down": 0,
    "suspected_update": 75,
    "high_risk": 20,
}

RISK_PENALTY = {
    "low": 0,
    "medium": 10,
    "high": 24,
}


def grade_for(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    return "C"


def recalculate_resource_score(session: Session, resource: Resource) -> ResourceScore:
    mentions = list(resource.mentions)
    source_ids = {mention.article.source_id for mention in mentions}
    source_count = len(source_ids)
    multi_source = min(source_count / 5, 1) * 100

    trust_values = [mention.article.source.trust_weight for mention in mentions]
    source_trust = (sum(trust_values) / len(trust_values) * 100) if trust_values else 60

    interaction_values = []
    for mention in mentions:
        article = mention.article
        if article.read_count is None and article.like_count is None and article.comment_count is None:
            interaction_values.append(50)
        else:
            score = 50
            if (article.read_count or 0) >= 5000:
                score += 25
            elif (article.read_count or 0) >= 1000:
                score += 15
            if (article.like_count or 0) >= 100:
                score += 15
            if (article.comment_count or 0) >= 20:
                score += 10
            interaction_values.append(min(score, 100))
    interaction = sum(interaction_values) / len(interaction_values) if interaction_values else 50

    if resource.last_mentioned_at:
        days = max((datetime.utcnow() - resource.last_mentioned_at).days, 0)
        freshness = max(0, 100 - days * 2)
    else:
        freshness = 50

    availability = STATUS_SCORE.get(resource.current_status, 65)
    evidence = 100 if mentions and any(resource.links) else 75 if mentions else 0
    risk_penalty = RISK_PENALTY.get(resource.risk_level, 0)

    total = 0.25 * multi_source + 0.25 * source_trust + 0.10 * interaction + 0.10 * freshness
    total += 0.15 * availability + 0.15 * evidence - risk_penalty
    total = round(min(max(total, 0), 100), 1)
    grade = grade_for(total)
    explanation = (
        f"该资源被 {source_count} 个公众号推荐，来源可信度均分 {source_trust:.0f}；"
        f"当前状态为 {resource.current_status}，风险等级 {resource.risk_level}，因此获得 {grade} 级评分。"
    )

    score = ResourceScore(
        id=new_id("score"),
        resource_id=resource.id,
        total_score=total,
        grade=grade,
        multi_source_score=round(multi_source, 1),
        source_trust_score=round(source_trust, 1),
        interaction_score=round(interaction, 1),
        freshness_score=round(freshness, 1),
        availability_score=round(availability, 1),
        evidence_score=round(evidence, 1),
        risk_penalty=round(risk_penalty, 1),
        explanation=explanation,
    )
    resource.latest_score = total
    resource.latest_grade = grade
    session.add(score)
    return score

