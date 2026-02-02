Sample Configs
==============

Multi-Container Web Challenge
-----------------------------

This challenge uses Redis and NGINX containers in addition to the main ``app``
container. The containers communicate with each other by host name. Adapted from
`Viper`_ from `redpwnCTF 2020`_.

.. code-block:: yaml

    name: viper
    author: Jim
    description: |-
      Don't you want your own ascii viper? No? Well here is Viper as a Service.
      If you experience any issues, send it
      [here](https://admin-bot.redpwnc.tf/submit?challenge=viper)

      Site: {{link}}

    flag:
      file: ./app/flag.txt

    provide:
      - ./viper.tar.gz

    containers:
      app:
        build: ./app
        resources:
          limits:
            cpu: 100m
            memory: 100M
        ports: [31337]
      nginx:
        build: ./nginx
        resources:
          limits:
            cpu: 100m
            memory: 100M
        ports: [80]
      redis:
        image: redis
        resources:
          limits:
            cpu: 100m
            memory: 100M
        ports: [6379]

    expose:
      nginx:
        - target: 80
          http: viper

Using Multiple Backends
-----------------------

This example shows an ``rcds.yaml`` with both Kubernetes and Instancer backends,
and a ``challenge.yaml`` that specifies which backend to use.

.. code-block:: yaml

    # rcds.yaml
    docker:
      image:
        prefix: gcr.io/project/ctf

    backends:
    - resolve: k8s
      options:
        kubeContext: gke_project_zone_cluster
        domain: challs.example.com
    - resolve: instancer
      options:
        url: https://instancer.example.com
        login_secret_key: ...
    
    defaultContainerBackend: k8s

.. code-block:: yaml

    # challenge.yaml (for an on-demand challenge)
    name: on-demand-pwn
    author: Jim
    description: |-
      Connect to the challenge: {{link}}
    
    backend: instancer
    
    instancer:
      per_team: true
      lifetime: 900

    containers:
      main:
        build: ./chall
        ports: [1337]
    
    expose:
      main:
      - target: 1337
        tcp: true

.. _config-samples#gke-rctf-gitlab:

GKE and rCTF on GitLab CI
-------------------------

This is the configuration used for `redpwnCTF 2020`_.

.. code-block:: yaml

    # rcds.yaml
    docker:
      image:
        prefix: gcr.io/project/ctf/2020

    flagFormat: flag\{[a-zA-Z0-9_,.'?!@$<>*:-]*\}

    defaults:
      containers:
        resources:
          limits:
            cpu: 100m
            memory: 150Mi
          requests:
            cpu: 10m
            memory: 30Mi

    backends:
    - resolve: k8s
      options:
        kubeContext: gke_project_zone_cluster
        domain: challs.2020.example.com
        annotations:
          ingress:
            traefik.ingress.kubernetes.io/router.tls: "true"
            traefik.ingress.kubernetes.io/router.middlewares: "ingress-nocontenttype@kubernetescrd"
    - resolve: rctf
      options:
        scoring:
          minPoints: 100
          maxPoints: 500

.. code-block:: yaml

    # .gitlab-ci.yml
    image: google/cloud-sdk:slim

    services:
      - docker:dind

    stages:
      - deploy

    variables:
      DOCKER_HOST: tcp://docker:2375
      RCDS_RCTF_URL: https://2020.example.com/

    before_script:
      - pip3 install rcds
      - gcloud auth activate-service-account service-account@project.iam.gserviceaccount.com --key-file=$GCLOUD_SA_TOKEN
      - gcloud config set project project
      - gcloud auth configure-docker gcr.io --quiet
      - gcloud container clusters get-credentials cluster --zone=zone

    deploy:
      stage: deploy
      when: manual
      environment:
        name: production
      script:
        - rcds deploy

The config creates Kubernetes Ingress objects compatible with Traefik, and
references the following middleware CRD exists to disable Traefik's
Content-Type auto-detection (change the name and namespace, both in the CRD and
the ingress annotation, to suit your setup):

.. code-block:: yaml

    apiVersion: traefik.containo.us/v1alpha1
    kind: Middleware
    metadata:
      name: nocontenttype
      namespace: ingress
    spec:
      contentType:
        autoDetect: false

.. _Viper: https://github.com/redpwn/redpwnctf-2020-challenges/blob/master/web/viper/challenge.yaml
.. _redpwnCTF 2020: https://2020.redpwn.net/
