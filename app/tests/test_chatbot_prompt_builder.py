from django.test import SimpleTestCase

from app.services.chatbot.prompt_builder import (
    build_designer_instructor_system_prompt,
    get_designer_instructor_persona_status,
)


class ChatbotPromptBuilderTests(SimpleTestCase):
    def test_build_designer_instructor_system_prompt_replaces_runtime_placeholders(self):
        prompt = build_designer_instructor_system_prompt(
            admin_name="지민",
            store_name="미르AI 합정점",
            current_date="2026-04-08",
            extra_context="고객에게 유지 난이도도 함께 설명하세요.",
        )

        self.assertIn("지민", prompt)
        self.assertIn("미르AI 합정점", prompt)
        self.assertIn("2026-04-08", prompt)
        self.assertIn("고객에게 유지 난이도도 함께 설명하세요.", prompt)
        self.assertIn("[응답 형식]", prompt)
        self.assertIn("인사, 감사, 짧은 확인 질문", prompt)
        self.assertNotIn("{{ADMIN_NAME}}", prompt)

    def test_persona_status_reports_template_path(self):
        status = get_designer_instructor_persona_status()

        self.assertIn("template_path", status)
        self.assertTrue(status["template_path"].endswith("designer_instructor_persona.md"))
