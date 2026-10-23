from dpp.sse import Channel

crowd_channel = Channel()


async def publish_questionnaire_status(questionnaire_id: str, status: str) -> None:
    await crowd_channel.publish("crowd.questionnaire_status_changed", {"questionnaire_id": questionnaire_id, "status": status})


async def publish_response_received(questionnaire_id: str, total: int) -> None:
    await crowd_channel.publish("crowd.response_received", {"questionnaire_id": questionnaire_id, "total": total})
