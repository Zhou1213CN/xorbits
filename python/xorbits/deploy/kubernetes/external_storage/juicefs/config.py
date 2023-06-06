from typing import Optional

from xorbits.deploy.kubernetes.config import KubeConfig


class SecretConfig(KubeConfig):
    """
    Configuration builder for Juicefs secret
    """

    _default_kind = "Secret"
    api_version = "v1"

    def __init__(
        self,
        kind: Optional[str] = None,
        metadata_url: str = "",
    ):
        self._kind = kind or self._default_kind
        self._metadata_url = metadata_url

    def build(self):
        return {
            "kind": self._kind,
            "metadata": {"name": "juicefs-secret"},
            "type": "Opaque",
            "stringData": {
                "name": "myjfs",
                "metaurl": self._metadata_url,
                "storage": "file",
                "bucket": "/var",
            },
        }


class PersistentVolumeConfig(KubeConfig):
    """
    Juicefs persistent volume builder
    """

    _default_kind = "PersistentVolume"
    api_version = "v1"

    def __init__(
        self,
        namespace: str,
        kind: Optional[str] = None,
    ):
        self._namespace = namespace
        self._kind = kind or self._default_kind

    def build(self):
        return {
            "kind": self._kind,
            "metadata": {
                "name": "juicefs-pv",
                "labels": {"juicefs-name": "ten-pb-fs"},
            },
            "spec": {
                "capacity": {"storage": "10Pi"},
                # For now, JuiceFS CSI Driver doesn't support setting storage capacity. Fill in any valid string is
                # fine. ( Reference: https://juicefs.com/docs/csi/guide/pv/ )
                "volumeMode": "Filesystem",
                "accessModes": ["ReadWriteMany"],
                "persistentVolumeReclaimPolicy": "Retain",
                "csi": {
                    "driver": "csi.juicefs.com",
                    "volumeHandle": "juicefs-pv",
                    "fsType": "juicefs",
                    "nodePublishSecretRef": {
                        "name": "juicefs-secret",
                        "namespace": self._namespace,
                    },
                },
            },
        }


class PersistentVolumeClaimConfig(KubeConfig):
    """
    Juicefs persistent volume claim builder
    """

    _default_kind = "PersistentVolumeClaim"
    api_version = "v1"

    def __init__(
        self,
        namespace: str,
        kind: Optional[str] = None,
    ):
        self._namespace = namespace
        self._kind = kind or self._default_kind

    def build(self):
        return {
            "kind": self._kind,
            "metadata": {"name": "juicefs-pvc", "namespace": self._namespace},
            "spec": {
                "accessModes": ["ReadWriteMany"],
                "volumeMode": "Filesystem",
                "storageClassName": "",
                "resources": {"requests": {"storage": "10Pi"}},
                "selector": {"matchLabels": {"juicefs-name": "ten-pb-fs"}},
            },
        }