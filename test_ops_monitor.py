import unittest

from deploy.ops_monitor import (
    count_ai_upstream_auth_failures,
    count_costly_ai_requests,
    evaluate_metrics,
)


class OpsMonitorTest(unittest.TestCase):
    def test_healthy_metrics_emit_no_alerts(self):
        metrics = {
            "wenxin_active": True,
            "nginx_active": True,
            "health_ok": True,
            "disk_used_percent": 40.0,
            "memory_used_percent": 50.0,
            "tls_days_remaining": 30.0,
            "backup_age_hours": 2.0,
            "backup_integrity": "ok",
            "sms_count": 3,
            "sms_limit": 20,
            "sms_month_count": 20,
            "sms_month_limit": 200,
            "ai_count": 50,
            "ai_auth_failures": 0,
        }

        self.assertEqual(evaluate_metrics(metrics), [])

    def test_thresholds_name_each_failed_control(self):
        metrics = {
            "wenxin_active": False,
            "nginx_active": False,
            "health_ok": False,
            "disk_used_percent": 85.0,
            "memory_used_percent": 90.0,
            "tls_days_remaining": 21.0,
            "backup_age_hours": 36.0,
            "backup_integrity": "corrupt",
            "sms_count": 16,
            "sms_limit": 20,
            "sms_month_count": 160,
            "sms_month_limit": 200,
            "ai_count": 100,
            "ai_auth_failures": 1,
        }

        names = {alert.split(":", 1)[0] for alert in evaluate_metrics(metrics)}

        self.assertEqual(
            names,
            {
                "wenxin_service",
                "nginx_service",
                "health",
                "disk",
                "memory",
                "tls",
                "backup_age",
                "backup_integrity",
                "sms_usage",
                "sms_month_usage",
                "ai_usage",
                "ai_upstream_auth",
            },
        )

    def test_monthly_sms_budget_warns_at_eighty_percent(self):
        metrics = {
            "wenxin_active": True,
            "nginx_active": True,
            "health_ok": True,
            "disk_used_percent": 40.0,
            "memory_used_percent": 50.0,
            "tls_days_remaining": 30.0,
            "backup_age_hours": 2.0,
            "backup_integrity": "ok",
            "sms_count": 3,
            "sms_limit": 100,
            "sms_month_count": 160,
            "sms_month_limit": 200,
            "ai_count": 10,
            "ai_auth_failures": 0,
        }

        self.assertIn(
            "sms_month_usage: 160/200 sends",
            evaluate_metrics(metrics),
        )

    def test_ai_cost_count_excludes_rejected_requests(self):
        logs = "\n".join(
            [
                '127.0.0.1 "POST /ai/chat HTTP/1.1" 200 20',
                '127.0.0.1 "POST /ai/chat HTTP/1.1" 422 20',
                '127.0.0.1 "POST /ai/chat HTTP/1.1" 401 20',
                '127.0.0.1 "POST /ai/chat HTTP/1.1" 400 20',
                '127.0.0.1 "GET /health HTTP/1.1" 200 20',
            ]
        )

        self.assertEqual(count_costly_ai_requests(logs), 2)

    def test_ai_upstream_auth_failure_is_detected(self):
        logs = "\n".join(
            [
                "[ai_chat] upstream HTTP status=401",
                "[ai_chat] upstream HTTP status=403",
                "[ai_chat] upstream HTTP status=429",
            ]
        )

        self.assertEqual(count_ai_upstream_auth_failures(logs), 2)


if __name__ == "__main__":
    unittest.main()
