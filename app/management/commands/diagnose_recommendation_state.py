from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from app.api.v1.services_django import build_recommendation_diagnostic_snapshot
from app.services.model_team_bridge import get_client_by_identifier, get_client_by_phone


class Command(BaseCommand):
    help = "Inspect recommendation readiness and diagnostic signals for one client without mutating runtime state."

    def add_arguments(self, parser):
        parser.add_argument("--client-id", type=str, help="Canonical backend client id")
        parser.add_argument("--legacy-client-id", type=str, help="Legacy client id")
        parser.add_argument("--phone", type=str, help="Client phone number")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print JSON output")

    def handle(self, *args, **options):
        client = self._resolve_client(options)
        snapshot = build_recommendation_diagnostic_snapshot(client)
        if options["as_json"]:
            self.stdout.write(json.dumps(snapshot, ensure_ascii=False, indent=2))
            return
        self._write_text_report(snapshot)

    def _resolve_client(self, options):
        client_id = str(options.get("client_id") or "").strip()
        legacy_client_id = str(options.get("legacy_client_id") or "").strip()
        phone = str(options.get("phone") or "").strip()

        identifiers = [value for value in (client_id, legacy_client_id, phone) if value]
        if not identifiers:
            raise CommandError("Provide one of --client-id, --legacy-client-id, or --phone.")
        if len(identifiers) > 1:
            raise CommandError("Provide only one identifier at a time.")

        if client_id:
            client = get_client_by_identifier(identifier=client_id)
        elif legacy_client_id:
            client = get_client_by_identifier(identifier=legacy_client_id)
        else:
            client = get_client_by_phone(phone=phone)

        if client is None:
            raise CommandError("Client could not be resolved from the provided identifier.")
        return client

    def _write_text_report(self, snapshot: dict) -> None:
        client = snapshot.get("client") or {}
        ai_runtime = snapshot.get("ai_runtime") or {}
        survey = snapshot.get("survey") or {}
        capture_attempt = snapshot.get("capture_attempt") or {}
        capture = snapshot.get("capture") or {}
        analysis = snapshot.get("analysis") or {}
        legacy = snapshot.get("legacy_recommendations") or {}
        predicted = snapshot.get("predicted_response") or {}

        self.stdout.write(self.style.SUCCESS(
            f"Recommendation diagnostics for client {client.get('client_id')} ({client.get('legacy_client_id')})"
        ))
        self.stdout.write(f"- name: {client.get('name') or '-'}")
        self.stdout.write(f"- phone: {client.get('phone') or '-'}")
        self.stdout.write("")

        self.stdout.write("AI runtime:")
        self.stdout.write(f"- configured_provider: {ai_runtime.get('configured_provider')}")
        self.stdout.write(f"- resolved_provider: {ai_runtime.get('resolved_provider')}")
        self.stdout.write(f"- service_enabled: {ai_runtime.get('service_enabled')}")
        self.stdout.write(f"- runpod_enabled: {ai_runtime.get('runpod_enabled')}")
        self.stdout.write("")

        self.stdout.write("Inputs:")
        self.stdout.write(
            f"- survey: present={survey.get('present')} target_length={survey.get('target_length')} target_vibe={survey.get('target_vibe')}"
        )
        self.stdout.write(
            f"- capture_attempt: present={capture_attempt.get('present')} status={capture_attempt.get('status')} reason_code={capture_attempt.get('reason_code')}"
        )
        self.stdout.write(
            f"- capture: present={capture.get('present')} status={capture.get('status')} record_id={capture.get('record_id')}"
        )
        self.stdout.write(
            f"- analysis: present={analysis.get('present')} face_shape={analysis.get('face_shape')} golden_ratio_score={analysis.get('golden_ratio_score')}"
        )
        self.stdout.write("")

        self.stdout.write("Legacy recommendation state:")
        self.stdout.write(f"- count: {legacy.get('count')}")
        self.stdout.write(f"- latest_batch_id: {legacy.get('latest_batch_id') or '-'}")
        self.stdout.write(f"- sources: {', '.join(legacy.get('sources') or []) or '-'}")
        self.stdout.write(f"- chosen_count: {legacy.get('chosen_count')}")
        self.stdout.write(f"- active_consultation: {snapshot.get('active_consultation')}")
        self.stdout.write(f"- local_mock_enabled: {snapshot.get('local_mock_enabled')}")
        self.stdout.write("")

        self.stdout.write("Predicted current_recommendations response:")
        self.stdout.write(f"- status: {predicted.get('status')}")
        self.stdout.write(f"- source: {predicted.get('source')}")
        self.stdout.write(f"- decision: {predicted.get('decision')}")
        self.stdout.write(f"- next_actions: {', '.join(predicted.get('next_actions') or []) or '-'}")
        self.stdout.write(f"- blockers: {', '.join(predicted.get('blockers') or []) or '-'}")
        self.stdout.write(f"- message: {predicted.get('message') or '-'}")
