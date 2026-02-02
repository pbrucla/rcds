``instancer`` --- Cyber Instancer
=============================

This backend deploys challenges to a `cyber-instancer <https://github.com/acmcyber/cyber-instancer>`_ instance.
It supports on-demand challenge instances, per-team isolation, and resource management.

Configuration
-------------

The backend requires authentication credentials and the URL of the instancer API.
These can be provided in ``rcds.yaml`` or via environment variables.

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

The following environment variables can override the configuration in ``rcds.yaml``:

- ``RCDS_INSTANCER_URL``: Overrides ``url``.
- ``RCDS_INSTANCER_LOGIN_SECRET_KEY``: Overrides ``login_secret_key``.
- ``RCDS_INSTANCER_ADMIN_TEAM_ID``: Overrides ``admin_team_id``.

Challenge Configuration
-----------------------

This backend supports standard rCDS challenge configuration, including:

- **Containers**: Define containers with ``image``, ``build``, ``ports``, and ``environment``.
- **Expose**: Expose ports via ``tcp`` or ``http``.
  
  - ``tcp`` ports are exposed directly.
  - ``http`` ports are exposed via subdomains. If a ``domain`` is configured in the backend options, it is appended to the subdomain.
- **Resources**: CPU and memory limits/requests are supported in the standard Kubernetes format (e.g., ``100m`` CPU, ``128Mi`` memory).

In addition, this backend adds an ``instancer`` section to ``challenge.yaml`` for configuring instance behavior.

.. code-block:: yaml

    instancer:
      per_team: true
      lifetime: 900
      boot_time: 15

- ``per_team`` (boolean, default: ``true``): Whether each team gets their own isolated instance.
  If ``false``, all teams share a single instance.
- ``lifetime`` (integer, default: ``900``): How long (in seconds) an instance lives before it is terminated.
  Teams can renew the instance to extend the lifetime.
- ``boot_time`` (integer, default: ``15``): Time (in seconds) to wait after starting before showing connection information to the user.
  Useful for challenges that need time to initialize.

.. _backends/instancer#reference:

Options Reference
-----------------

.. jsonschema:: ../../../rcds/backends/instancer/options.schema.yaml

Raw schema:

.. literalinclude:: ../../../rcds/backends/instancer/options.schema.yaml
    :language: yaml
