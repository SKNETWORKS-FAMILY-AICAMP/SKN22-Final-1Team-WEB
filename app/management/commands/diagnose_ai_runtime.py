from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from app.services.ai_facade import (
    build_ai_runtime_diagnostic_snapshot,
    build_model_connection_validation_snapshot,
)


class Command(BaseCommand):
    help = "Inspect current AI provider resolution, health state, and backend-only warnings."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print JSON output")
        parser.add_argument("--no-cache", action="store_true", dest="no_cache", help="Bypass cached AI health state")
        parser.add_argument("--probe", action="store_true", dest="probe", help="Run repeated health probes and summarize model connectivity")
        parser.add_argument("--attempts", type=int, default=3, help="Number of repeated probes to run with --probe")

    def handle(self, *args, **options):
        if options["probe"]:
            payload = build_model_connection_validation_snapshot(
                attempts=options["attempts"],
                use_cache=not options["no_cache"],
            )
            if options["as_json"]:
                self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
                return
            self._write_probe_text_report(payload)
            return

        payload = build_ai_runtime_diagnostic_snapshot(use_cache=not options["no_cache"])
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        self._write_text_report(payload)

    def _write_text_report(self, payload: dict) -> None:
        config = payload.get("config") or {}
        health = payload.get("health") or {}
        warnings = payload.get("warnings") or []

        self.stdout.write(self.style.SUCCESS("AI runtime diagnostics"))
        self.stdout.write("Configuration:")
        self.stdout.write(f"- configured_provider: {config.get('configured_provider')}")
        self.stdout.write(f"- resolved_provider: {config.get('resolved_provider')}")
        self.stdout.write(f"- service_enabled: {config.get('service_enabled')}")
        self.stdout.write(f"- service_url_configured: {config.get('service_url_configured')}")
        self.stdout.write(f"- service_token_configured: {config.get('service_token_configured')}")
        self.stdout.write(f"- service_api_version: {config.get('service_api_version') or '-'}")
        self.stdout.write(f"- runpod_enabled: {config.get('runpod_enabled')}")
        self.stdout.write(f"- runpod_api_key_configured: {config.get('runpod_api_key_configured')}")
        self.stdout.write(f"- runpod_endpoint_id_configured: {config.get('runpod_endpoint_id_configured')}")
        self.stdout.write("")

        self.stdout.write("Health:")
        self.stdout.write(f"- mode: {health.get('mode')}")
        self.stdout.write(f"- status: {health.get('status')}")
        self.stdout.write(f"- message: {health.get('message')}")
        self.stdout.write(f"- cached: {health.get('cached')}")
        self.stdout.write("")

        self.stdout.write("Warnings:")
        if warnings:
            for item in warnings:
                self.stdout.write(f"- {item}")
        else:
            self.stdout.write("- none")

    def _write_probe_text_report(self, payload: dict) -> None:
        config = payload.get("config") or {}
        summary = payload.get("summary") or {}
        probes = payload.get("probes") or []
        warnings = payload.get("warnings") or []

        self.stdout.write(self.style.SUCCESS("AI model connectivity probe"))
        self.stdout.write("Configuration:")
        self.stdout.write(f"- configured_provider: {config.get('configured_provider')}")
        self.stdout.write(f"- resolved_provider: {config.get('resolved_provider')}")
        self.stdout.write(f"- service_enabled: {config.get('service_enabled')}")
        self.stdout.write(f"- runpod_enabled: {config.get('runpod_enabled')}")
        self.stdout.write("")

        self.stdout.write("Summary:")
        self.stdout.write(f"- attempts: {summary.get('attempts')}")
        self.stdout.write(f"- overall_state: {summary.get('overall_state')}")
        self.stdout.write(f"- online_count: {summary.get('online_count')}")
        self.stdout.write(f"- offline_count: {summary.get('offline_count')}")
        self.stdout.write(f"- face_analysis_mode: {summary.get('face_analysis_mode')}")
        self.stdout.write(f"- recommendation_mode: {summary.get('recommendation_mode')}")
        self.stdout.write(f"- connectivity_state: {summary.get('connectivity_state')}")
        self.stdout.write(f"- inference_status: {summary.get('inference_status')}")
        self.stdout.write(f"- sync_contract_state: {summary.get('sync_contract_state')}")
        self.stdout.write(f"- metadata_state: {summary.get('metadata_state')}")
        self.stdout.write(f"- queue_state: {summary.get('queue_state')}")
        self.stdout.write(f"- last_error_code: {summary.get('last_error_code') or '-'}")
        self.stdout.write(f"- last_error_message: {summary.get('last_error_message') or '-'}")
        self.stdout.write("")

        inference_probe = payload.get("inference_probe") or {}
        self.stdout.write("Inference Probe:")
        if inference_probe:
            self.stdout.write(f"- status: {inference_probe.get('status')}")
            self.stdout.write(f"- inference_status: {inference_probe.get('inference_status')}")
            self.stdout.write(f"- sync_contract_state: {inference_probe.get('sync_contract_state')}")
            self.stdout.write(f"- metadata_state: {inference_probe.get('metadata_state')}")
            self.stdout.write(f"- queue_state: {inference_probe.get('queue_state')}")
            self.stdout.write(f"- elapsed_ms: {inference_probe.get('elapsed_ms')}")
            self.stdout.write(f"- job_status: {inference_probe.get('job_status') or '-'}")
            self.stdout.write(f"- last_error_code: {inference_probe.get('last_error_code') or '-'}")
            self.stdout.write(f"- message: {inference_probe.get('message')}")
        else:
            self.stdout.write("- none")
        self.stdout.write("")

        self.stdout.write("Probes:")
        for probe in probes:
            self.stdout.write(
                "- attempt={attempt} mode={mode} status={status} elapsed_ms={elapsed_ms} message={message}".format(
                    attempt=probe.get("attempt"),
                    mode=probe.get("mode"),
                    status=probe.get("status"),
                    elapsed_ms=probe.get("elapsed_ms"),
                    message=probe.get("message"),
                )
            )
        if not probes:
            self.stdout.write("- none")
        self.stdout.write("")

        self.stdout.write("Warnings:")
        if warnings:
            for item in warnings:
                self.stdout.write(f"- {item}")
        else:
            self.stdout.write("- none")
