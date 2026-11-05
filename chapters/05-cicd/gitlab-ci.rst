.. _ch05_gitlab_ci:

GitLab CI: A Brief Comparison
==============================

Many companies, especially those that self-host their source code, use GitLab instead of
GitHub. The concepts from this chapter carry over almost unchanged. The syntax and some
defaults differ. This page maps one to the other so you can read and write a
``.gitlab-ci.yml`` file in your first week at such a job.

-----

The Model
----------

GitLab CI is configured by **one file**, ``.gitlab-ci.yml``, at the repository root (as
opposed to any number of files in ``.github/workflows/``). Its central concept is the
**stage**:

.. code-block:: text

   stages:   check                      build               deploy
             ┌──────────┐               ┌─────────────────┐ ┌────────────────┐
             │ lint     │               │ build-and-push  │ │ deploy-staging │
             │ test     │ ──all pass──▶ │                 │─▶────────────────│
             │ test-pg  │               │                 │ │ deploy-prod ▶  │ (manual)
             └──────────┘               └─────────────────┘ └────────────────┘

Jobs in the same stage run in parallel. A stage starts when **all** jobs of the previous
stage succeed. That gives you a sensible graph without writing any dependencies. When you
need finer control, ``needs:`` turns the pipeline into a graph, just like GitHub
Actions.

Every job runs in a **container**: ``image:`` picks it, per job or as a default. GitHub
Actions jobs run directly on a VM unless you ask for a container. On GitLab, the
container is the default.

-----

Concept Map
------------

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Concept
     - GitHub Actions
     - GitLab CI
   * - Config location
     - ``.github/workflows/*.yml`` (many files)
     - ``.gitlab-ci.yml`` (one file, can ``include:`` others)
   * - Ordering
     - ``needs:`` between jobs (parallel by default)
     - ``stages:`` (plus optional ``needs:``)
   * - Execution environment
     - ``runs-on:`` a VM
     - ``image:`` a container on a runner
   * - Conditional execution
     - ``on:`` triggers + ``if:`` expressions
     - ``workflow: rules:`` + per-job ``rules:`` (legacy: ``only`` / ``except``)
   * - Reusable steps
     - Actions (``uses: owner/repo@ref``)
     - Templates: ``extends:``, ``include:``, CI/CD components
   * - Shell commands
     - ``run:``
     - ``script:`` (+ ``before_script:`` / ``after_script:``)
   * - Database for tests
     - ``services:`` (reach via ``localhost``)
     - ``services:`` (reach via the service's ``alias`` hostname)
   * - Dependency cache
     - ``actions/cache`` or ``setup-python`` ``cache:``
     - ``cache: key: files: [...]``
   * - Job outputs to keep
     - ``actions/upload-artifact``
     - ``artifacts:`` (incl. ``reports:`` the MR page understands)
   * - Container registry
     - ``ghcr.io`` + ``GITHUB_TOKEN``
     - Built-in per project: ``$CI_REGISTRY_IMAGE`` + ``$CI_REGISTRY_PASSWORD``
   * - Internal package index
     - ``PIP_INDEX_URL`` from a repository variable; GitHub Packages has no PyPI registry
     - ``PIP_INDEX_URL`` from a CI/CD variable; every project has a built-in PyPI package registry
   * - Secrets
     - Secrets (repo / environment)
     - CI/CD variables marked **Masked** and **Protected**
   * - Manual approval
     - Environment with required reviewers
     - ``when: manual`` job (play button), protected environments
   * - Cancel superseded runs
     - ``concurrency: cancel-in-progress``
     - ``interruptible: true`` + project setting
   * - Merge gate
     - Branch protection + required checks
     - Protected branch + "Pipelines must succeed"

-----

The BookShelf Pipeline, Side by Side
-------------------------------------

The same lint job in both systems:

.. code-block:: yaml

   # GitHub Actions (.github/workflows/ci.yml)
   lint:
     name: lint
     runs-on: ubuntu-24.04
     steps:
       - uses: actions/checkout@v7
       - uses: actions/setup-python@v7
         with:
           python-version: "3.12"
           cache: pip
           cache-dependency-path: requirements-dev.lock
       - run: pip install -r requirements-dev.lock
       - run: make lint
       - run: make typecheck

.. code-block:: yaml

   # GitLab CI (.gitlab-ci.yml)
   lint:
     stage: check
     image: python:3.12.16-trixie
     variables:
       PIP_CACHE_DIR: $CI_PROJECT_DIR/.cache/pip
     cache:
       key:
         files: [requirements-dev.lock]
       paths: [.cache/pip]
     before_script:
       - pip install -r requirements-dev.lock
       - pip install --no-deps -e .
     script:
       - make lint
       - make typecheck

Differences worth noticing:

- **No checkout step.** GitLab clones the repository into the job automatically.
- **No setup-python.** The container image *is* the Python version. Pinning
  ``python:3.12.16-trixie`` gives the exact interpreter of the production image, which
  is arguably better than ``setup-python``'s "latest 3.12".
- **The cache path must be inside the project directory.** GitLab only caches paths
  under ``$CI_PROJECT_DIR``, hence ``PIP_CACHE_DIR``.

The full GitLab equivalent of ``ci.yml`` **and** ``cd.yml`` fits in one file. Here it is,
from ``support/.gitlab-ci.yml``:

.. code-block:: yaml

   # The BookShelf pipeline in GitLab CI, for comparison with
   # .github/workflows/ci.yml and cd.yml. Not used by the labs.
   stages: [check, build, deploy]

   # Run for merge requests and for the default branch, nothing else.
   workflow:
     rules:
       - if: $CI_PIPELINE_SOURCE == "merge_request_event"
       - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

   default:
     interruptible: true

   # Hidden job (leading dot): a template the check jobs extend.
   .python:
     stage: check
     image: python:3.12.16-trixie
     variables:
       PIP_CACHE_DIR: $CI_PROJECT_DIR/.cache/pip
     cache:
       key:
         files: [requirements-dev.lock]
       paths: [.cache/pip]
     before_script:
       - pip install -r requirements-dev.lock
       - pip install --no-deps -e .

   lint:
     extends: .python
     script:
       - make lint
       - make typecheck

   test:
     extends: .python
     script:
       - make coverage
     coverage: '/^TOTAL.+?(\d+%)$/'
     artifacts:
       when: always
       expire_in: 14 days
       reports:
         coverage_report:
           coverage_format: cobertura
           path: coverage.xml

   test-pg:
     extends: .python
     services:
       - name: postgres:16-alpine
         alias: postgres
     variables:
       POSTGRES_USER: test
       POSTGRES_PASSWORD: test
       POSTGRES_DB: bookshelf_test
       TEST_DATABASE_URL: postgresql://test:test@postgres:5432/bookshelf_test
     script:
       - pytest tests/

   # Merge requests: check that the image builds, push nothing.
   build:
     stage: build
     image: docker:29.9-cli
     services: [docker:29.9-dind]
     variables:
       DOCKER_TLS_CERTDIR: /certs
     rules:
       - if: $CI_PIPELINE_SOURCE == "merge_request_event"
     script:
       - docker build -t bookshelf:$CI_COMMIT_SHA .

   # Default branch: build once and push to the project's built-in registry.
   build-and-push:
     stage: build
     image: docker:29.9-cli
     services: [docker:29.9-dind]
     variables:
       DOCKER_TLS_CERTDIR: /certs
     rules:
       - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
     script:
       - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
       - >-
         docker build
         --label org.opencontainers.image.revision=$CI_COMMIT_SHA
         -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA"
         -t "$CI_REGISTRY_IMAGE:latest" .
       - docker push --all-tags "$CI_REGISTRY_IMAGE"

   deploy-staging:
     stage: deploy
     image: alpine:3.24
     needs: [build-and-push]
     environment:
       name: staging
       url: https://staging.bookshelf.example.com
     rules:
       - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
     script:
       - test -n "$DEPLOY_TOKEN" || { echo "DEPLOY_TOKEN is not set"; exit 1; }
       - echo "Deploying $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA to staging"

   deploy-production:
     stage: deploy
     image: alpine:3.24
     needs: [deploy-staging]
     environment:
       name: production
       url: https://bookshelf.example.com
     rules:
       - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
         when: manual          # a "play" button; the pipeline waits for a human
     script:
       - test -n "$DEPLOY_TOKEN" || { echo "DEPLOY_TOKEN is not set"; exit 1; }
       - echo "Deploying $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA to production"

-----

What Differs in Practice
-------------------------

**rules instead of triggers.** GitHub decides *whether a workflow runs* with ``on:``.
GitLab creates a pipeline for (almost) every push and decides *which jobs* it contains
with ``rules:``. The ``workflow: rules:`` block at the top limits pipelines to merge
requests and the default branch. Without it, a push to a branch with an open merge
request creates **two** pipelines, one for the branch and one for the MR. Older
configurations use ``only:`` / ``except:``. They still work but cannot express
everything ``rules:`` can, and GitLab recommends ``rules:`` for new configurations.

**One pipeline, not two.** GitHub needed a second workflow and the ``workflow_run``
trigger, with all its pitfalls, to run CD after CI. In GitLab, the deploy stage is part
of the same pipeline and simply comes after the build stage. There is no head-SHA
confusion: every job in a pipeline sees the same ``$CI_COMMIT_SHA``.

**Building images needs Docker-in-Docker.** Jobs already run inside a container, so
``docker build`` needs a Docker daemon of its own: the ``docker:dind`` service. It must
run **privileged**, which the runner administrator has to allow. Many organisations do
not allow it on shared runners and use daemonless builders instead (Buildah, or
BuildKit in rootless mode). On GitHub-hosted runners, Docker is simply there.

**The registry comes with the project.** Every GitLab project has a container registry,
and every job gets short-lived credentials for it in ``$CI_REGISTRY_USER`` /
``$CI_REGISTRY_PASSWORD``. ``$CI_REGISTRY_IMAGE`` is already the lowercase image path,
so the lowercase step from :ref:`ch05_docker_in_ci` is unnecessary.

**Secrets are variables with flags.** In **Settings → CI/CD → Variables**, a variable
can be **Masked** (hidden in logs, with the same limits as on GitHub) and **Protected**
(only exposed to pipelines on protected branches and tags). *Protected* is GitLab's
equivalent of "fork PRs get no secrets": a feature branch pipeline cannot read the
production deploy token, even if someone edits ``.gitlab-ci.yml`` on that branch.

**Manual gates are jobs.** ``when: manual`` shows a play button on the pipeline. Anyone
allowed to run it can deploy. **Protected environments** restrict who may deploy to
``production``, the equivalent of required reviewers. Some approval features are
reserved for paid GitLab tiers.

**Merge requests show reports inline.** ``artifacts: reports: coverage_report`` makes
GitLab annotate the MR diff with which changed lines are covered. The ``coverage:``
regex extracts the percentage from the ``TOTAL`` line of the job log and displays it on
the MR. GitHub needs third-party actions or services for both.

.. admonition:: Observation:

   The concepts carry over completely: pipelines as code in the repository, cheap
   checks before expensive ones, pinned images and tools, a test database as a
   service container, an image built once and tagged with the commit, secrets scoped
   to protected branches, a human gate before production, and a merge gate enforced
   by the server. If you can explain *why* each piece of ``ci.yml`` and ``cd.yml``
   exists, picking up GitLab's syntax takes an afternoon.
