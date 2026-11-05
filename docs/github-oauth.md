# GitHub OAuth setup

1. GitHub → **Settings → Developer settings → OAuth Apps → New OAuth App**.
   - Homepage URL: your `PUBLIC_APP_URL` (e.g. `http://localhost:3000`).
   - Authorization callback URL: `PUBLIC_APP_URL` + `/github/callback` (e.g. `http://localhost:3000/github/callback`). This is a web-app page; it posts the code to `POST /api/v1/github/complete`.
2. Copy the client ID and generate a client secret.
3. Generate an encryption key for tokens at rest:

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. In `.env` (server side only):

   ```env
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   TOKEN_ENCRYPTION_KEY=...
   GITHUB_OAUTH_SCOPES=repo          # or public_repo for public repositories only
   ```

5. Restart the API and the worker. **GitHub → Connect GitHub** in the web app starts the flow.

**Key rotation:** set `TOKEN_ENCRYPTION_KEY=new-key,old-key`. New tokens use the first key; existing ones still decrypt. Remove the old key once every user has reconnected.

**GitHub Enterprise:** set `GITHUB_WEB_URL` and `GITHUB_API_URL`.

## Permissions

OAuth Apps cannot be limited to selected repositories. `repo` is the narrowest scope that can push branches to private repositories; `public_repo` restricts Fixify to public ones. A GitHub App would allow per-repository `contents:write` and `pull_requests:write`. That is listed as a future improvement in [security.md](security.md).

## API calls Fixify makes

| Purpose | Endpoint |
|---|---|
| Profile and scopes | `GET /user` |
| Repositories and branches | `GET /user/repos`, `GET /repos/{r}`, `GET /repos/{r}/branches`, `GET /repos/{r}/git/ref/heads/{b}` |
| Reading | `GET /repos/{r}/git/trees/{sha}?recursive=1`, `GET /repos/{r}/git/blobs/{sha}` |
| Writing (approved fixes only) | `POST /repos/{r}/git/blobs`, `/git/trees`, `/git/commits`, `/git/refs` (new `fixify/…` branch), `POST /repos/{r}/pulls` |
| Status | `GET /repos/{r}/pulls?head=…`, `GET /repos/{r}/pulls/{n}` |
| Disconnect | `DELETE /applications/{client_id}/grant` |

Rate limiting (403 with `x-ratelimit-remaining: 0`, or 429) is reported to the user, and retried for background jobs.
