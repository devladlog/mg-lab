def container(k8s):
    return k8s["Deployment"]["spec"]["template"]["spec"]["containers"][0]


def test_probes_match_the_container_apps_ones(k8s):
    c = container(k8s)
    assert c["startupProbe"]["httpGet"]["path"] == "/healthz/live"
    assert c["readinessProbe"]["httpGet"]["path"] == "/healthz/ready"
    assert c["livenessProbe"]["httpGet"]["path"] == "/healthz/live"
    assert c["ports"] == [{"name": "http", "containerPort": 8080}]


def test_runs_locked_down(k8s):
    pod = k8s["Deployment"]["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["automountServiceAccountToken"] is False
    sc = container(k8s)["securityContext"]
    assert sc["allowPrivilegeEscalation"] is False and sc["readOnlyRootFilesystem"] is True
    assert sc["capabilities"]["drop"] == ["ALL"]
    # read-only root needs a writable /tmp
    assert {"name": "tmp", "mountPath": "/tmp"} in container(k8s)["volumeMounts"]


def test_requests_and_memory_limit_are_set(k8s):
    r = container(k8s)["resources"]
    assert r["requests"]["cpu"] and r["requests"]["memory"] and r["limits"]["memory"]


def test_rolling_update_never_drops_below_desired(k8s):
    s = k8s["Deployment"]["spec"]["strategy"]
    assert s["rollingUpdate"]["maxUnavailable"] == 0


def test_drain_fits_in_the_termination_grace_period(k8s):
    # app: 5 s drain + up to 25 s host shutdown timeout = 30 s
    assert k8s["Deployment"]["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] >= 30


def test_service_hpa_and_pdb_point_at_the_deployment(k8s):
    labels = k8s["Deployment"]["spec"]["template"]["metadata"]["labels"]
    assert k8s["Service"]["spec"]["selector"] == labels
    assert k8s["Service"]["spec"]["ports"][0]["targetPort"] == "http"
    assert k8s["HorizontalPodAutoscaler"]["spec"]["scaleTargetRef"]["name"] == k8s["Deployment"]["metadata"]["name"]
    assert k8s["HorizontalPodAutoscaler"]["spec"]["minReplicas"] >= 2
    assert k8s["PodDisruptionBudget"]["spec"]["selector"]["matchLabels"] == labels


def test_image_is_a_placeholder_filled_by_the_deploy_script(k8s):
    assert container(k8s)["image"] == "ACR_LOGIN_SERVER/contoso/orders-api:IMAGE_TAG"
