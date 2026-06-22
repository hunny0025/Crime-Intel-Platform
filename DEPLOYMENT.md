# Deployment Guide — Crime Intel Platform

This guide explains how to deploy the **Crime Intel Platform** backend services, databases, and microservices to **Render**, and the Next.js frontend to **Vercel**.

---

## 1. Backend, Databases, and Microservices on Render

We have provided a unified `render.yaml` blueprint configuration in the root directory. This template sets up:
1. **PostgreSQL Database** (`crime-intel-postgres`)
2. **Neo4j Graph Database** (`crime-intel-neo4j`) with a persistent volume
3. **MinIO Object Storage** (`crime-intel-minio`) with a persistent volume
4. **OSINT Service** (`crime-intel-osint`)
5. **Main FastAPI Backend Application** (`crime-intel-backend`)

### Setup & Deployment Steps

1. **Push your code** to a private or public GitHub/GitLab repository.
2. Sign in to your **[Render Dashboard](https://dashboard.render.com/)**.
3. Click **New** (top right) and select **Blueprint**.
4. Connect your GitHub/GitLab repository.
5. Render will automatically parse the `render.yaml` file. Review the service configurations and click **Apply**.
6. The services will deploy in order:
   - Databases and storage services (`postgres`, `neo4j`, `minio`) deploy first.
   - OSINT and the main FastAPI Backend build and launch.

### Environment Variables & Customization

The blueprint uses secure default credentials. You should change these in production:
* **`NEO4J_PASSWORD`**: Defaults to `crimeintel2024`.
* **`MINIO_ROOT_PASSWORD`**: Defaults to `minioadmin`.
* **`ALLOWED_ORIGINS`**: Update this to include your Vercel frontend URL (e.g., `["https://your-frontend.vercel.app"]`).
* **`SKIP_WAIT_DEPENDENCIES`**: Set to `true` (default in blueprint) to ensure fast deployment. If you wish to enforce blocking waits for external message brokers, you can change this.
* **`KAFKA_BOOTSTRAP_SERVERS`**: To connect an external Kafka broker (such as Upstash Kafka or Confluent Cloud), supply the server URL here.

---

## 2. Next.js Frontend on Vercel

Vercel provides native, optimized hosting for Next.js applications.

### Setup & Deployment Steps

1. Sign in to your **[Vercel Dashboard](https://vercel.com/)**.
2. Click **Add New** and select **Project**.
3. Import your GitHub/GitLab repository containing the project.
4. Set the **Root Directory** to `crime-intel-frontend`.
5. Configure the **Build & Development Settings**:
   - Framework Preset: **Next.js**
   - Build Command: `next build`
   - Output Directory: `.next`
6. Add the following **Environment Variables**:
   * `NEXT_PUBLIC_API_URL`: The URL of your deployed `crime-intel-backend` service on Render (e.g., `https://crime-intel-backend.onrender.com`).
   * `NEXT_PUBLIC_OSINT_URL`: The URL of your deployed `crime-intel-osint` service on Render (e.g., `https://crime-intel-osint.onrender.com`).
   * `ANTHROPIC_API_KEY`: *(Optional)* Your Anthropic Claude API Key for the Copilot feature. If not provided, the frontend will automatically use local rule-based heuristics.
7. Click **Deploy**.

---

## 3. Production Hardening Checklist

- [ ] **Database Dialects**: The platform automatically sanitizes any connection strings starting with `postgres://` to `postgresql://` to prevent SQLAlchemy startup crashes on Render.
- [ ] **Security Headers**: The frontend includes a pre-configured `vercel.json` applying strict security policies (including Frame Options, Content-Security-Policy, and nosniff).
- [ ] **Authentication**: Ensure the `API_SECRET_KEY` env variable is set to a secure 32-character string on the backend for API access control.
