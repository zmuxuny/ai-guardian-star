"""Authenticated local board feedback API. No device or MQTT construction."""
import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Body


def create_care_router(runtime, token_provider=None):
    token_provider = token_provider or (lambda: os.environ.get(runtime.config.token_env, ''))
    def authenticate(request: Request):
        token = token_provider()
        if not token:
            raise HTTPException(503, 'care_token_not_configured')
        scheme, _, supplied = request.headers.get('authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not secrets.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(401, 'invalid_care_credentials')

    router = APIRouter(prefix='/api/care', dependencies=[Depends(authenticate)])
    @router.get('/shadow-report')
    def shadow_report():
        return {'schema_version': 1, 'mode':runtime.config.mode, 'reports':runtime.shadow_reports()}
    def scope(model_version, person_id):
        if model_version != runtime.config.model_version or person_id not in runtime.config.person_ids:
            raise HTTPException(404, 'care_scope_not_found')

    @router.get('/{model_version}/{person_id}/events')
    def events(model_version: str, person_id: str):
        scope(model_version, person_id)
        return {'schema_version': 1, 'events': runtime.events(person_id), 'state': runtime.state(person_id)}

    @router.get('/{model_version}/{person_id}/feedback')
    def feedback_list(model_version: str, person_id: str, status: str = 'active'):
        scope(model_version, person_id)
        try:
            return {'feedback': runtime.store(person_id).feedback_for_mode(runtime.config.mode, status=status)}
        except ValueError:
            raise HTTPException(422, 'invalid_feedback_status') from None

    @router.post('/{model_version}/{person_id}/events/{event_id}/feedback')
    def feedback(model_version: str, person_id: str, event_id: str, body: dict = Body(...)):
        scope(model_version, person_id)
        if set(body) - {'payload','operation','reason'}:
            raise HTTPException(422, 'feedback_target_and_time_are_immutable')
        try:
            return runtime.feedback(person_id, event_id, body.get('payload'),
                                    operation=body.get('operation', 'submit'), reason=body.get('reason', ''))
        except LookupError:
            raise HTTPException(404, 'care_event_not_found') from None
        except ValueError:
            raise HTTPException(422, 'invalid_feedback') from None
        except Exception:
            raise HTTPException(503, 'feedback_storage_unavailable') from None
    return router
