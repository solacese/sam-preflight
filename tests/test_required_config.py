from sam_preflight.checks.config import (
    evaluate_persistence_config,
    evaluate_required_config,
)
from sam_preflight.models import CheckStatus


def _base_values() -> dict:
    return {
        "sam": {
            "dnsName": "sam.example.com",
            "sessionSecretKey": "super-secret",
        },
        "broker": {
            "url": "wss://broker.messaging.solace.cloud:443",
            "clientUsername": "user",
            "password": "pass",
            "vpn": "vpn",
        },
        "llmService": {
            "planningModel": "gpt-4o",
            "generalModel": "gpt-4o",
            "reportModel": "gpt-4o",
            "imageModel": "dall-e-3",
            "transcriptionModel": "whisper-1",
            "llmServiceEndpoint": "https://api.openai.com/v1",
            "llmServiceApiKey": "sk-test",
        },
    }


def test_required_config_passes_when_present() -> None:
    result = evaluate_required_config(_base_values())
    assert result.status == CheckStatus.PASS


def test_required_config_warns_on_missing_values() -> None:
    values = _base_values()
    values["broker"]["password"] = ""

    result = evaluate_required_config(values)

    assert result.status == CheckStatus.WARN
    assert "broker.password" in result.details


def test_external_persistence_warns_if_application_password_missing() -> None:
    values = _base_values()
    values["global"] = {"persistence": {"enabled": False}}
    values["dataStores"] = {
        "database": {
            "host": "db",
            "port": "5432",
            "adminUsername": "postgres",
            "adminPassword": "admin",
            "applicationPassword": "",
        },
        "s3": {
            "endpointUrl": "https://s3.amazonaws.com",
            "bucketName": "artifacts",
            "connectorSpecBucketName": "connectors",
            "accessKey": "access",
            "secretKey": "secret",
        },
    }

    result = evaluate_persistence_config(values)

    assert result.status == CheckStatus.WARN
    assert "dataStores.database.applicationPassword" in result.details


def test_bundled_persistence_warns_without_storage_class() -> None:
    values = _base_values()
    values["global"] = {"persistence": {"enabled": True, "namespaceId": "sam"}}
    values["persistence-layer"] = {
        "postgresql": {"resources": {"requests": {"cpu": "200m", "memory": "256Mi"}}},
        "seaweedfs": {"resources": {"requests": {"cpu": "200m", "memory": "128Mi"}}},
    }

    result = evaluate_persistence_config(values)

    assert result.status == CheckStatus.WARN
    assert "storageClassName" in result.details
