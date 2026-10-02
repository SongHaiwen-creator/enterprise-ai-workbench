from uuid import uuid4


def case_body(category: str = "refusal_behavior") -> dict:
    expected = {
        "knowledge_qa": {
            "routing_intent": "knowledge_qa",
            "answer_status": "answered",
            "citation_requirement": "present",
        },
        "tool_calling": {
            "routing_intent": "tool_request",
            "outcome": "not_executed",
            "tool_key": None,
            "approval_required": False,
            "non_execution_reason": "no_available_tool",
        },
        "permission_boundary": {
            "actor_role": "employee",
            "actor_membership_status": "active",
            "target_context": "other_workspace",
            "operation": "agent_route",
            "expected_http_status": 404,
            "result_category": "not_found",
            "access_denied": True,
        },
        "refusal_behavior": {
            "routing_intent": "unsupported",
            "response_category": "unsupported_request",
            "safe_response_required": True,
        },
    }[category]
    body = {
        "name": "Synthetic case",
        "case_type": category,
        "test_input": "Synthetic input",
        "expected_behavior": expected,
    }
    if category == "knowledge_qa":
        body["knowledge_base_id"] = str(uuid4())
    return body
