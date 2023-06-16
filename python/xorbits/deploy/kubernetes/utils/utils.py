import glob
import logging
import os
import shutil
import subprocess
import subprocess as sp
import tempfile
import uuid
from contextlib import contextmanager
from distutils.spawn import find_executable

import numpy as np

from .... import numpy as xnp
from ...._mars.utils import lazy_import
from ....utils import get_local_py_version
from .. import new_cluster

logger = logging.getLogger(__name__)

XORBITS_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(xnp.__file__)))
)
TEST_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCKER_ROOT = os.path.join((os.path.dirname(os.path.dirname(TEST_ROOT))), "docker")

kubernetes = lazy_import("kubernetes")
k8s = lazy_import("kubernetes")

juicefs_available = "juicefs" in sp.getoutput(
    "kubectl get pods --all-namespaces -o wide | grep 'juicefs-csi'"
)

kube_available = (
    find_executable("kubectl") is not None
    and find_executable("docker") is not None
    and k8s is not None
)


def _collect_coverage():
    dist_coverage_path = os.path.join(XORBITS_ROOT, ".dist-coverage")
    if os.path.exists(dist_coverage_path):
        # change ownership of coverage files
        if find_executable("sudo"):  # pragma: no cover
            proc = subprocess.Popen(
                [
                    "sudo",
                    "-n",
                    "chown",
                    "-R",
                    f"{os.geteuid()}:{os.getegid()}",
                    dist_coverage_path,
                ],
                shell=False,
            )
            proc.wait()

        # rewrite paths in coverage result files
        for fn in glob.glob(os.path.join(dist_coverage_path, ".coverage.*")):
            if "COVERAGE_FILE" in os.environ:  # pragma: no cover
                new_cov_file = os.environ["COVERAGE_FILE"] + os.path.basename(
                    fn
                ).replace(".coverage", "")
            else:  # pragma: no cover
                new_cov_file = fn.replace(".dist-coverage" + os.sep, "")
            shutil.copyfile(fn, new_cov_file)
        shutil.rmtree(dist_coverage_path)


def _build_docker_images(py_version: str):
    image_name = "xorbits-test-image:" + uuid.uuid1().hex
    xorbits_root = XORBITS_ROOT + "/"
    docker_file_path = os.path.join(DOCKER_ROOT, "Dockerfile")[len(xorbits_root) :]
    try:
        build_proc = subprocess.Popen(
            [
                "docker",
                "build",
                "-f",
                docker_file_path,
                "-t",
                image_name,
                ".",
                "--build-arg",
                f"PYTHON_VERSION={py_version}",
            ],
            cwd=XORBITS_ROOT,
        )
        if build_proc.wait() != 0:  # pragma: no cover
            raise SystemError("Executing docker build failed.")
    except:  # noqa: E722  # pragma: no cover
        _remove_docker_image(image_name)
        raise
    return image_name


def _remove_docker_image(image_name, raises=True):
    if "CI" not in os.environ:  # pragma: no cover
        # delete image iff in CI environment
        return
    proc = subprocess.Popen(["docker", "rmi", "-f", image_name])
    if proc.wait() != 0 and raises:
        raise SystemError("Executing docker rmi failed.")  # pragma: no cover


def _load_docker_env():
    proc = subprocess.Popen(["minikube", "docker-env"], stdout=subprocess.PIPE)
    proc.wait(30)
    for line in proc.stdout:
        line = line.decode().split("#", 1)[0]
        line = line.strip()  # type: str | bytes
        export_pos = line.find("export")
        if export_pos < 0:
            continue
        line = line[export_pos + 6 :].strip()
        var, value = line.split("=", 1)
        os.environ[var] = value.strip('"')

    ingress_proc = subprocess.Popen(["minikube", "addons", "enable", "ingress"])
    if ingress_proc.wait() != 0:  # pragma: no cover
        raise SystemError("Enable ingress failed!")


@contextmanager
def _start_kube_cluster(**kwargs):
    py_version = get_local_py_version()
    _load_docker_env()
    image_name = _build_docker_images(py_version)
    logger.info("image_name")
    logger.info(image_name)
    temp_spill_dir = tempfile.mkdtemp(prefix="test-xorbits-k8s-")
    api_client = k8s.config.new_client_from_config()
    kube_api = k8s.client.CoreV1Api(api_client)

    cluster_client = None
    try:
        cluster_client = new_cluster(
            api_client,
            image=image_name,
            worker_spill_paths=[temp_spill_dir],
            timeout=600,
            log_when_fail=True,
            **kwargs,
        )

        assert cluster_client.endpoint is not None
        assert cluster_client.session is not None
        assert cluster_client.session.session_id.startswith(cluster_client.namespace)

        pod_items = kube_api.list_namespaced_pod(cluster_client.namespace).to_dict()

        log_processes = []
        for item in pod_items["items"]:
            log_processes.append(
                subprocess.Popen(
                    [
                        "kubectl",
                        "logs",
                        "-f",
                        "-n",
                        cluster_client.namespace,
                        item["metadata"]["name"],
                    ]
                )
            )
        yield cluster_client
        [p.terminate() for p in log_processes]
    finally:
        shutil.rmtree(temp_spill_dir)
        if cluster_client:
            try:
                cluster_client.stop(wait=True, timeout=20)
            except TimeoutError:
                pass
        _collect_coverage()
        _remove_docker_image(image_name, False)


def simple_job():
    a = xnp.ones((100, 100), chunk_size=30) * 2 * 1 + 1
    b = xnp.ones((100, 100), chunk_size=20) * 2 * 1 + 1
    c = (a * b * 2 + 1).sum()
    print(c)

    expected = (np.ones(a.shape) * 2 * 1 + 1) ** 2 * 2 + 1
    np.testing.assert_array_equal(c.to_numpy(), expected.sum())
