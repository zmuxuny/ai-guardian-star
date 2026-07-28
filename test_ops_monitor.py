import unittest

from deploy.ops_monitor import count_costly_ai_requests, evaluate_metrics


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
            "ai_count": 50,
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
            "ai_count": 100,
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
                "ai_usage",
            },
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


if __name__ == "__main__":
    unittest.main()
