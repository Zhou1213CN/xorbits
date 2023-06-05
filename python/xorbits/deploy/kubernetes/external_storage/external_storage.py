from abc import ABC, abstractmethod
from typing import Optional

from kubernetes.client import ApiClient

from .juicefs.config import (
    PersistentVolumeClaimConfig,
    PersistentVolumeConfig,
    SecretConfig,
)


class ExternalStorage(ABC):
    def __init__(
        self, namespace: Optional[str], api_client: ApiClient, metadata_url: str = ""
    ):
        from kubernetes import client as kube_client

        self._namespace = namespace
        self._api_client = api_client
        self._core_api = kube_client.CoreV1Api(self._api_client)
        self._metadata_url = metadata_url

    @abstractmethod
    def build(self):
        """
        Build the external storage
        """


class JuicefsK8SStorage(ExternalStorage):
    def build(self):
        """
        Create pv, secret, and pvc
        """
        secret_config = SecretConfig(metadata_url=self._metadata_url)

        persistent_volume_config = PersistentVolumeConfig(namespace=self._namespace)

        persistent_volume_claim_config = PersistentVolumeClaimConfig(
            namespace=self._namespace
        )
        self._core_api.create_namespaced_secret(self._namespace, secret_config.build())
        self._core_api.create_persistent_volume(persistent_volume_config.build())
        self._core_api.create_namespaced_persistent_volume_claim(
            self._namespace, persistent_volume_claim_config.build()
        )
