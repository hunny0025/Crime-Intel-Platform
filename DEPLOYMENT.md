# Deployment Guide — Crime Intel Platform (100% Free Tier Setup)

This guide explains how to deploy the **Crime Intel Platform** backend services, databases, and microservices for **100% free** using **Render** (free tier), **Neo4j AuraDB** (free tier cloud graph), and **Vercel** (free frontend).

The platform automatically runs without local MinIO or Kafka servers by falling back to built-in thread-safe in-memory event queues and local filesystem directory storage.

---

## 1. Backend, Databases, and Microservices on Render

We have provided a streamlined `render.yaml` blueprint configuration in the root directory. This template sets up:
1. **PostgreSQL Database** (`crime-intel-postgres`)
2. **OSINT Service** (`crime-intel-osint`)
3. **Main FastAPI Backend Application** (`crime-intel-backend`)

### Setup & Deployment Steps

#### Step 1: Create a Free Neo4j Aura Database (Graph Database)
1. Sign up for a free account at **[Neo4j Aura Console](https://console.neo4j.io/)** (no credit card required).
2. Click **Create instance**, choose **AuraDB Free**, and select a region close to you.
3. Save the generated credentials file:
   - **Connection URL**: e.g., `neo4j+s://xxxxxx.databases.neo4j.io`
   - **Username**: `neo4j`
   - **Password**: e.g., `xxxxxxxxxxxxxxxxxxxx`
4. Wait 1-2 minutes for the database instance to initialize.

#### Step 2: Deploy to Render
1. **Push your code** to your public/private GitHub or GitLab repository.
2. Sign in to your **[Render Dashboard](https://dashboard.render.com/)**.
3. Click **New** (top right) and select **Blueprint**.
4. Connect your GitHub/GitLab repository.
5. Render will automatically parse the `render.yaml` file.
6. Under the blueprint environment variable inputs, configure:
   - **`NEO4J_URI`**: The Connection URL from Neo4j Aura Console (e.g. `neo4j+s://xxxxxx.databases.neo4j.io`).
   - **`NEO4J_PASSWORD`**: The password from Neo4j Aura Console.
   - **`BACKEND_URL`**: Once deployed, the URL of your backend web service (e.g., `https://crime-intel-backend.onrender.com`).
   - **`ALLOWED_ORIGINS`**: Enter your frontend origins as a JSON array (e.g. `["http://localhost:3000", "https://your-frontend.vercel.app"]`).
7. Click **Apply**. Render will deploy the services.

---

## 2. Next.js Frontend on Vercel

Vercel provides native, optimized hosting for Next.js applications on their free tier.

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

- [x] **Automatic Storage Fallback**: When `MINIO_ENDPOINT` is set to `local` (default in render.yaml), the backend automatically saves and streams files directly from the container's storage folder, bypassing the need for a MinIO cluster.
- [x] **Automatic Event Broker Fallback**: When `KAFKA_BOOTSTRAP_SERVERS` is empty (default in render.yaml), the backend uses a local, multi-threaded publish-subscribe broker to communicate case/graph events between processing workers.
- [x] **Security Headers**: The frontend includes a pre-configured `vercel.json` applying strict security policies (including Frame Options, Content-Security-Policy, and nosniff).
- [ ] **Authentication**: Ensure the `API_SECRET_KEY` env variable is set to a secure 32-character string on the backend for API access control.

