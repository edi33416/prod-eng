.. _ch05_docker_in_ci:

Building and Pushing Docker Images in CI
=========================================

.. admonition:: Crash Course: Container Registries
   :class: dropdown

   A **registry** is an HTTP server that stores images and hands them out. You have used
   one since Chapter 4: every ``FROM python:...`` and ``docker pull postgres`` talked to
   Docker Hub.

   **Push/pull model.** ``docker push`` uploads the layers the registry does not have yet,
   then a **manifest** listing them. ``docker pull`` downloads the manifest, then any
   layers missing locally. Layers are content-addressed (named by their SHA-256), so
   shared base layers are stored and transferred once.

   **Naming.** A full image reference has up to five parts:

   .. code-block:: text

      ghcr.io / student / bookshelf : 4f1c2a9e… @sha256:7216b579…
      └──┬──┘   └──┬──┘   └──┬───┘   └───┬───┘  └──────┬───────┘
      registry  namespace  repository   tag          digest

   Omitted parts get defaults: no registry means ``docker.io``, and a Docker Hub
   image with no namespace lives in ``library/``. That is why ``postgres:16-alpine`` is
   really:

   .. code-block:: bash

      $ docker image inspect postgres:16-alpine --format '{{index .RepoDigests 0}}'
      postgres@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab
      $ docker pull postgres:16-alpine
      16-alpine: Pulling from library/postgres
      Digest: sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab
      Status: Image is up to date for postgres:16-alpine

   **Tag vs digest.** A tag is a mutable pointer: anyone with push rights can point
   ``16-alpine`` at a new image tomorrow. A digest is the hash of the manifest itself and
   can never refer to different content. Pull by digest (``postgres@sha256:…``) when you
   need to be certain.

   **Authentication.** ``docker login <registry>`` stores a credential that ``push``
   (and ``pull`` of private images) uses. Without a credential helper,
   ``~/.docker/config.json`` stores it **base64-encoded, not encrypted**. Treat that file
   like a password.

   **Docker Hub vs ghcr.io.** Docker Hub is the default public registry and rate-limits
   anonymous pulls, which shared CI runners hit regularly. GitHub Container Registry
   (``ghcr.io``) is built into GitHub, is free for public images, and accepts the
   workflow's own ``GITHUB_TOKEN``, so no extra secret is needed. Companies usually run
   a private registry as well. You will set up Harbor in Chapter 10.

   For a deeper dive, see: `OCI Distribution Specification <https://github.com/opencontainers/distribution-spec/blob/main/spec.md>`_

-----

Why CI Builds the Images
-------------------------

In Chapter 4 you built images on your laptop. Imagine pushing those to production:

- The image contains whatever was in your **working tree**, including uncommitted
  changes and files ``.gitignore`` skips but ``.dockerignore`` does not. Nobody can
  rebuild it.
- Nothing proves the image passed the tests. You may have built it before running
  them, or from a different branch.
- It was built on ``arm64`` (Apple Silicon) while the servers run ``amd64``.
- The registry password lives on every developer's laptop.

When CI builds the image, all four problems go away. Every image comes from a commit,
built on a clean machine, after the checks passed, with a token that expires when the
job ends. The commit SHA in the tag links each image to the exact source it was built
from.

-----

The ``build-and-push`` Job
---------------------------

Add this job to ``cd.yml``, before the deploy jobs. It replaces the ``if:`` on
``deploy-staging`` (the guard now lives here) and gives the deploy jobs an image to
deploy:

.. code-block:: yaml

   env:
     REGISTRY: ghcr.io
     # The commit CI tested. github.sha would be the latest commit on main,
     # which is not necessarily the one that passed.
     GIT_SHA: ${{ github.event.workflow_run.head_sha }}

   jobs:
     build-and-push:
       name: build-and-push
       # Only commits that passed CI, that were pushed to this repository's main
       # (a fork's PR from a branch called "main" also matches branches: [main]).
       if: >-
         github.event.workflow_run.conclusion == 'success' &&
         github.event.workflow_run.event == 'push' &&
         github.event.workflow_run.head_repository.full_name == github.repository
       runs-on: ubuntu-24.04
       timeout-minutes: 15
       permissions:
         contents: read
         packages: write
       outputs:
         image: ${{ steps.image.outputs.name }}:${{ github.event.workflow_run.head_sha }}
       steps:
         - uses: actions/checkout@v7
           with:
             ref: ${{ env.GIT_SHA }}
         # Image names must be lowercase; GitHub user and repo names need not be.
         - name: Compute image name
           id: image
           run: echo "name=${REGISTRY}/${GITHUB_REPOSITORY,,}" >> "$GITHUB_OUTPUT"
         - uses: docker/setup-buildx-action@v4
         - uses: docker/login-action@v4
           with:
             registry: ${{ env.REGISTRY }}
             username: ${{ github.actor }}
             password: ${{ secrets.GITHUB_TOKEN }}
         - name: Build and push
           uses: docker/build-push-action@v7
           with:
             context: .
             push: true
             tags: |
               ${{ steps.image.outputs.name }}:${{ env.GIT_SHA }}
               ${{ steps.image.outputs.name }}:latest
             labels: |
               org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
               org.opencontainers.image.revision=${{ env.GIT_SHA }}
             cache-from: type=gha
             cache-to: type=gha,mode=max

Step by step:

``permissions: packages: write``
   The workflow default is ``contents: read``. Pushing to ``ghcr.io`` needs the
   ``packages: write`` scope, and only this job gets it. The deploy jobs keep the
   read-only default.

``checkout`` with ``ref: GIT_SHA``
   Without ``ref:``, a ``workflow_run`` job checks out the latest commit on ``main``,
   which may be newer than the one CI tested. Building that commit would push an image
   that never passed CI.

**Compute image name**
   ``GITHUB_REPOSITORY`` is ``Owner/Repo`` with the original capitalisation. Image
   names must be lowercase, so ``ghcr.io/JaneDoe/BookShelf`` is rejected with
   ``ERROR: invalid tag "ghcr.io/JaneDoe/BookShelf:…": repository name must be
   lowercase``. ``${VAR,,}`` is the
   bash way to lowercase a string. Writing a line ``name=value`` to the file
   ``$GITHUB_OUTPUT`` creates a **step output**, which later steps read as
   ``steps.image.outputs.name``.

``docker/login-action``
   Logs in to ``ghcr.io`` with the job's ``GITHUB_TOKEN``. No personal access token and
   no repository secret are needed, and the token expires when the job ends. The action
   logs out again in its post-job step.

``labels``
   OCI labels are metadata baked into the image. ``image.source`` links the package
   to the repository on GitHub, so the package shows up on the repository page and
   inherits its access settings. ``image.revision`` records the commit, so anyone
   holding the image can find its source.

``outputs: image``
   A **job output**, readable by downstream jobs as
   ``needs.build-and-push.outputs.image``. This is how the deploy jobs learn exactly
   which image to deploy.

-----

Build Once, Deploy Many
------------------------

Update both deploy jobs to depend on ``build-and-push`` and to deploy **its** image:

.. code-block:: yaml

   deploy-staging:
     name: deploy-staging
     needs: build-and-push
     # ... runs-on, timeout-minutes, environment unchanged ...
     steps:
       - name: Deploy to staging
         env:
           IMAGE: ${{ needs.build-and-push.outputs.image }}
           DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
         run: |
           if [ -z "$DEPLOY_TOKEN" ]; then
             echo "::error::DEPLOY_TOKEN is not set for the staging environment"
             exit 1
           fi
           echo "Deploying $IMAGE to staging"
           # A real deployment would use $DEPLOY_TOKEN here, e.g. to call a
           # deploy API or SSH to the host and run: docker compose pull && up -d

   deploy-production:
     name: deploy-production
     needs: [build-and-push, deploy-staging]
     # ... same pattern, "to production" ...

``deploy-production`` lists ``build-and-push`` in ``needs`` even though it already
depends on it through ``deploy-staging``. A job can only read the outputs of jobs it
lists **directly** in ``needs``.

The image is built **once**. Staging and production receive the same tag, which points
to the same digest: the bytes that ran in staging are the bytes that go to production.
The pipeline never rebuilds per environment. Configuration that differs between
environments (database URLs, credentials) is injected at runtime, as in Chapter 4,
never baked in.

The complete file is ``support/bookshelf-ch5-solution/.github/workflows/cd.yml``. It also
contains a ``PIP_INDEX_URL`` build argument, added in :ref:`ch05_internal_package_index`.

.. note::

   CI's ``build`` job and CD's ``build-and-push`` both build the image. That is not a
   violation of *build once*: CI's build is a check that is thrown away, and runs on pull
   requests too. CD's is the one artifact that gets deployed. Thanks to
   ``cache-from: type=gha``, the second build reuses almost every layer and takes
   seconds.

-----

A Push in the Logs
-------------------

After merging to ``main``, CI runs, then CD. The ``Build and push`` step ends with:

.. code-block:: text

   #14 exporting to image
   #14 exporting layers 1.9s done
   #14 exporting manifest sha256:0b8e5c… done
   #14 naming to ghcr.io/student/bookshelf:4f1c2a9e8b7d6c5f4e3a2b1c0d9e8f7a6b5c4d3e done
   #14 naming to ghcr.io/student/bookshelf:latest done
   #14 pushing layers 6.2s done
   #14 pushing manifest for ghcr.io/student/bookshelf:4f1c2a9e8b7d6c5f4e3a2b1c0d9e8f7a6b5c4d3e@sha256:91d3fa… 0.6s done
   #14 DONE 9.4s

The repository's front page now shows a **Packages** section in the right sidebar. Click
``bookshelf`` to see the tags, the pull command, and the labels.

.. warning::

   A package's visibility is separate from the repository's. If ``docker pull`` from a
   machine that is not logged in fails with ``unauthorized`` or ``denied``, the package
   is private. Either make it public under **Package settings → Danger Zone → Change
   visibility**, or ``docker login ghcr.io`` with a personal access token that has the
   ``read:packages`` scope. Never use a token with write scopes for pulling.

-----

Tagging Strategy
-----------------

.. list-table::
   :header-rows: 1
   :widths: 22 26 52

   * - Tag
     - Example
     - Purpose
   * - Git SHA
     - ``:4f1c2a9e8b7d…``
     - **Traceability.** One tag per commit, never reused. This is what you deploy and
       roll back to.
   * - ``latest``
     - ``:latest``
     - **Convenience** for humans trying the image. Moves on every push. Never deploy
       ``latest``: after the next push, a server restart silently changes the version.
   * - Semantic version
     - ``:1.4.2``, ``:1.4``
     - **Releases.** Built when you push a Git tag ``v1.4.2``. ``1.4`` moves to the
       newest patch release, which is useful for consumers who want fixes but no
       breaking changes.

Semver tags are produced on a different trigger (a pushed Git tag) and are easiest with
``docker/metadata-action``, which computes the tag list and labels for you:

.. code-block:: yaml

   # Sketch, not part of the solution workflows
   on:
     push:
       tags: ["v*.*.*"]
   # ...
       - id: meta
         uses: docker/metadata-action@v6
         with:
           images: ghcr.io/${{ github.repository }}
           tags: |
             type=semver,pattern={{version}}
             type=semver,pattern={{major}}.{{minor}}
             type=sha,format=long
       - uses: docker/build-push-action@v7
         with:
           push: true
           tags: ${{ steps.meta.outputs.tags }}
           labels: ${{ steps.meta.outputs.labels }}

**Rolling back** with SHA tags means deploying an **older SHA**, an image that already
exists and already passed CI. Nothing is rebuilt, and the rollback takes as long as a
deployment. Chapter 9 uses this when an alert fires after a bad release.

-----

Pull and Run the CI-Built Image
--------------------------------

On your machine, take the SHA from the CD run (or from the Packages page):

.. code-block:: bash

   $ docker pull ghcr.io/<you>/bookshelf:<sha>
   <sha>: Pulling from <you>/bookshelf
   ...
   Digest: sha256:91d3fa…
   Status: Downloaded newer image for ghcr.io/<you>/bookshelf:<sha>

   $ docker image inspect ghcr.io/<you>/bookshelf:<sha> --format '{{json .Config.Labels}}' \
       | python3 -m json.tool
   {
       "org.opencontainers.image.revision": "4f1c2a9e8b7d6c5f4e3a2b1c0d9e8f7a6b5c4d3e",
       "org.opencontainers.image.source": "https://github.com/student/bookshelf"
   }

   $ docker run -d --rm --name bookshelf-ci -p 8000:8000 ghcr.io/<you>/bookshelf:<sha>
   $ curl -s localhost:8000/health
   {"status":"ok"}
   $ docker stop bookshelf-ci

The ``revision`` label answers "which code is this?" without any external records. Given
only an image on a server, you can ``git checkout`` the exact source it was built from.

.. note::

   GitHub's standard ``ubuntu-24.04`` runners are ``x86_64``, so the image is
   ``linux/amd64``. On an Apple Silicon Mac, ``docker run`` prints
   ``WARNING: The requested image's platform (linux/amd64) does not match the detected
   host platform (linux/arm64/v8)`` and runs it under emulation: slower, but it works.
   To publish a multi-architecture image, add ``docker/setup-qemu-action@v4`` before
   Buildx and ``platforms: linux/amd64,linux/arm64`` to ``build-push-action``. The
   ``arm64`` half is then built under emulation, which is several times slower. If
   that becomes a problem, GitHub also offers native ``ubuntu-24.04-arm`` runners.

-----

**Exercises**

#. Add the ``build-and-push`` job to ``cd.yml`` and wire both deploy jobs to it as shown.
   Run ``actionlint``, then push to ``main``. Follow the run: CI → CD → staging →
   approval → production. Confirm that the ``Deploying ... to staging`` and ``to
   production`` lines print **the same** image reference.

#. Find the package in your repository's **Packages** sidebar. Make it public if
   necessary. Pull it on your machine by SHA, inspect its labels, run it, and call
   ``/health``. Then run ``git log -1 <revision>`` in your clone with the SHA from the
   ``revision`` label.

#. Pull the same image by **digest** instead of tag (copy the digest from the Packages
   page or from ``docker image inspect --format '{{index .RepoDigests 0}}'``). Why would
   a security-conscious deployment pin the digest rather than the SHA tag, even though
   both are unique?

#. Push two commits to ``main`` in quick succession. Look at the tags on the package
   page. Which tag does ``latest`` point to? Which tag would you deploy to roll back
   the second commit?

#. Change ``permissions: packages: write`` to ``packages: read`` on a scratch branch,
   merge it, and read the error from the push step. Restore it.

#. Compare the duration of the ``Build and push`` step on the first and the second
   CD run. Where in the log do you see BuildKit's cache being imported?

#. **(Optional)** Make the image multi-architecture (``linux/amd64,linux/arm64``) as
   described in the note above. How much longer does the build take? Run
   ``docker buildx imagetools inspect ghcr.io/<you>/bookshelf:latest`` to list the
   platforms in the manifest.
