# 🚀 CI/CD Pipeline Documentation

> **Binance Merchant Trading Flow - Jenkins CI/CD Pipeline**

## 📋 Mục Lục

- [Tổng Quan](#-tổng-quan)
- [Kiến Trúc Pipeline](#-kiến-trúc-pipeline)
- [Luồng CI/CD Chi Tiết](#-luồng-cicd-chi-tiết)
- [Branching Strategy](#-branching-strategy)
- [Environments](#-environments)
- [Timeline & Metrics](#-timeline--metrics)
- [Notification & Monitoring](#-notification--monitoring)
- [Rollback Strategy](#-rollback-strategy)
- [Setup Instructions](#-setup-instructions)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 Tổng Quan

Pipeline CI/CD này tự động hóa hoàn toàn quy trình **Build → Test → Deploy** cho hệ thống data engineering xử lý giao dịch Binance Merchant, bao gồm:

- **Apache Airflow**: Orchestration platform
- **Apache Spark**: Batch processing jobs
- **Apache Flink**: Real-time streaming
- **PostgreSQL, MinIO, Kafka**: Data infrastructure

### Mục Tiêu Chính

✅ **Automation**: Tự động hóa 95% quy trình deployment  
✅ **Quality Assurance**: Đảm bảo code quality & security qua nhiều gates  
✅ **Fast Feedback**: Developer nhận kết quả CI trong 20-30 phút  
✅ **Safe Deployment**: Zero-downtime deployment với rollback tự động  
✅ **Visibility**: Full traceability của mọi thay đổi  

---

## 🏗️ Kiến Trúc Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CI/CD ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────┘

GitHub Repository
       │
       │ (Webhook on Push/PR)
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                        JENKINS SERVER                             │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐      │
│  │              CONTINUOUS INTEGRATION (CI)               │      │
│  ├────────────────────────────────────────────────────────┤      │
│  │  1. Checkout & Validation                              │      │
│  │  2. Code Quality Checks (Parallel)                     │      │
│  │     ├─ Flake8 (Linting)                                │      │
│  │     ├─ Pylint (Static Analysis)                        │      │
│  │     ├─ Black (Formatting)                              │      │
│  │     └─ isort (Import Sorting)                          │      │
│  │  3. Security Scanning (Parallel)                       │      │
│  │     ├─ Bandit (Code Security)                          │      │
│  │     └─ Safety (Dependencies)                           │      │
│  │  4. Unit Tests + Coverage                              │      │
│  └────────────────────────────────────────────────────────┘      │
│                          │                                        │
│                          ▼                                        │
│  ┌────────────────────────────────────────────────────────┐      │
│  │         CONTINUOUS DELIVERY (CD) - BUILD               │      │
│  ├────────────────────────────────────────────────────────┤      │
│  │  5. Build Docker Images (Parallel)                     │      │
│  │     ├─ Airflow Image                                   │      │
│  │     ├─ Spark Processing Image                          │      │
│  │     └─ Flink Streaming Image                           │      │
│  │  6. Security Scan Images (Trivy)                       │      │
│  │  7. Push to Docker Registry                            │      │
│  └────────────────────────────────────────────────────────┘      │
│                          │                                        │
│                          ▼                                        │
│  ┌────────────────────────────────────────────────────────┐      │
│  │      CONTINUOUS DEPLOYMENT (CD) - DEPLOY               │      │
│  ├────────────────────────────────────────────────────────┤      │
│  │  8. Environment Selection                              │      │
│  │     ├─ Dev: No Deploy                                  │      │
│  │     ├─ Staging: Auto Deploy                            │      │
│  │     └─ Production: Manual Approval                     │      │
│  │  9. Deploy & Migration                                 │      │
│  │  10. Integration Tests                                 │      │
│  │  11. Health Checks                                     │      │
│  │  12. Performance Monitoring                            │      │
│  └────────────────────────────────────────────────────────┘      │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    TARGET ENVIRONMENTS                            │
├──────────────────────────────────────────────────────────────────┤
│  🟢 DEV          🟡 STAGING           🔴 PRODUCTION              │
│  (Local)        (Pre-prod)          (Live)                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Luồng CI/CD Chi Tiết

### **Phase 1: Continuous Integration (CI)**

#### Stage 1: Checkout & Validation (2-3 phút)
```
✓ Clone source code từ Git repository
✓ Validate build environment (Docker, Python, Git)
✓ Load environment configuration
✓ Display build metadata (version, commit hash, author)
```

#### Stage 2: Install Dependencies (3-5 phút)
```
✓ Create Python virtual environment
✓ Install production dependencies (requirements.txt)
✓ Install development tools (pytest, pylint, flake8, black)
```

#### Stage 3: Code Quality Checks (5-7 phút) - **PARALLEL**
```
├─ Flake8
│  └─ Check PEP8 compliance
│  └─ Max line length: 120 characters
│  └─ Generate linting report
│
├─ Pylint
│  └─ Static code analysis
│  └─ Minimum score: 7.0/10
│  └─ Check code complexity
│
├─ Black
│  └─ Verify code formatting
│  └─ Ensure consistent style
│
└─ isort
   └─ Check import ordering
   └─ Validate import structure
```

**Exit Criteria**: ⚠️ Warning only, không block pipeline

#### Stage 4: Security Scanning (3-5 phút) - **PARALLEL**
```
├─ Bandit
│  └─ Scan Python code for security issues
│  └─ Check for SQL injection, hardcoded passwords, etc.
│  └─ Generate security report (JSON)
│
└─ Safety
   └─ Check known vulnerabilities in dependencies
   └─ Scan against CVE database
   └─ Alert on high/critical issues
```

**Exit Criteria**: ⚠️ Warning only, không block pipeline

#### Stage 5: Unit Tests (5-10 phút)
```
✓ Run pytest test suite
✓ Execute unit tests for:
  ├─ Data ingestion components
  ├─ Data transformation logic
  ├─ Spark jobs
  └─ Flink streaming
✓ Generate coverage report
  └─ Minimum coverage: 70%
✓ Publish JUnit test results
✓ Publish HTML coverage dashboard
```

**Exit Criteria**: ❌ **FAIL → STOP PIPELINE**

---

### **Phase 2: Continuous Delivery (CD) - Build**

#### Stage 6: Build Docker Images (10-15 phút) - **PARALLEL**
```
📦 Image 1: Airflow Platform
   ├─ Base: apache/airflow:3.1.0-python3.10
   ├─ Copy: src/, dags/, configs/, scripts/
   ├─ Install: requirements.txt
   └─ Tag: {registry}/airflow:{build}-{commit-hash}

📦 Image 2: Spark Processing
   ├─ Base: bitnami/spark:3.5.0
   ├─ Copy: batch_transformation/
   ├─ Install: Spark dependencies
   └─ Tag: {registry}/spark:{build}-{commit-hash}

📦 Image 3: Flink Streaming
   ├─ Base: flink:1.18-java11
   ├─ Copy: streaming/, jars/
   ├─ Install: Flink connectors
   └─ Tag: {registry}/flink:{build}-{commit-hash}
```

#### Stage 7: Image Security Scan (5-7 phút)
```
✓ Trivy scan for each image
✓ Check for vulnerabilities:
  ├─ OS packages
  ├─ Python dependencies
  └─ Base image issues
✓ Generate security report
✓ Severity levels: HIGH, CRITICAL
```

**Exit Criteria**: ⚠️ Alert nếu có CRITICAL, continue deployment

#### Stage 8: Push to Registry (3-5 phút)
```
✓ Login to Docker Registry
✓ Push images với version tags
✓ Push images với 'latest' tag
✓ Verify upload success
```

---

### **Phase 3: Continuous Deployment (CD) - Deploy**

#### Stage 9: Deploy to Environment (5-10 phút)

##### 🟢 **DEV Environment (Feature Branches)**
```
❌ NO DEPLOYMENT
✓ Only run CI pipeline
✓ Verify code quality
✓ Run tests
Purpose: Fast feedback cho developers
```

##### 🟡 **STAGING Environment (Develop Branch)**
```
✅ AUTOMATIC DEPLOYMENT

1. Pre-deployment
   ├─ Backup current database
   ├─ Backup configurations
   └─ Tag current version for rollback

2. Deployment
   ├─ Export IMAGE_TAG environment variable
   ├─ Pull new Docker images
   ├─ Update docker-compose.yaml
   ├─ Run: docker-compose down
   ├─ Run: docker-compose up -d
   └─ Wait 30s for services to stabilize

3. Post-deployment
   ├─ Run Airflow DB migration
   ├─ Restart Airflow workers
   └─ Verify all containers running
```

##### 🔴 **PRODUCTION Environment (Main Branch)**
```
⏸️ MANUAL APPROVAL REQUIRED

1. Pre-approval
   ├─ Pipeline PAUSES
   ├─ Send notification to approvers
   ├─ Display deployment summary:
   │  ├─ Version to deploy
   │  ├─ Changes included
   │  ├─ Test results
   │  └─ Risk assessment
   └─ Wait for approval (timeout: 30 minutes)

2. Deployment (after approval)
   ├─ Full database backup
   ├─ Full configuration backup
   ├─ Blue-Green Deployment:
   │  ├─ Deploy new version (Green)
   │  ├─ Keep old version (Blue) running
   │  ├─ Run health checks on Green
   │  └─ Switch traffic Blue → Green
   ├─ Run database migrations
   └─ Update monitoring dashboards

3. Validation
   ├─ Verify all services healthy
   ├─ Check error rates
   └─ Monitor performance metrics
```

#### Stage 10: Integration Tests (3-5 phút)
```
✓ Test Airflow DAGs
  ├─ Verify DAG imports
  ├─ Test task dependencies
  └─ Validate DAG scheduling

✓ Test Data Pipeline
  ├─ Test Binance API connection
  ├─ Test data ingestion flow
  ├─ Verify Spark job execution
  └─ Validate Flink streaming

✓ Test Infrastructure
  ├─ PostgreSQL connectivity
  ├─ MinIO/S3 access
  ├─ Kafka connectivity
  └─ Redis availability
```

**Exit Criteria**: ❌ **FAIL → TRIGGER ROLLBACK**

#### Stage 11: Health Checks (2-3 phút)
```
✓ Airflow Web UI
  └─ GET /health → 200 OK

✓ Airflow Scheduler
  └─ Check SchedulerJob running

✓ Airflow Workers
  └─ Celery workers responding

✓ PostgreSQL
  └─ pg_isready → accepting connections

✓ Redis
  └─ redis-cli ping → PONG

✓ MinIO
  └─ mc admin info → service online
```

**Exit Criteria**: ❌ **FAIL → AUTOMATIC ROLLBACK**

#### Stage 12: Performance Monitoring (Ongoing)
```
✓ Monitor for 30 minutes:
  ├─ CPU usage < 80%
  ├─ Memory usage < 85%
  ├─ API response time < 2s
  ├─ Error rate < 1%
  └─ Queue depth normal
```

---

## 🌿 Branching Strategy

```
┌────────────────────────────────────────────────────────────┐
│                   GIT WORKFLOW                              │
└────────────────────────────────────────────────────────────┘

feature/add-binance-futures ─┐
                             │
feature/optimize-spark ──────┤
                             │
feature/kafka-consumer ──────┼──> develop ──> staging ──> main ──> production
                             │     (Auto)      (Test)     (Manual)    (Live)
feature/dashboard-ui ────────┤
                             │
hotfix/critical-bug ─────────┘


Branch              Environment     Deployment      Approval
─────────────────────────────────────────────────────────────
feature/*          None            No              No
develop            Staging         Auto            No
main               Production      Auto            Yes (Required)
hotfix/*           Staging         Auto            No → Production: Yes
```

### Branch Rules

#### **Feature Branches** (`feature/*`)
```
Purpose: Development của features mới
Naming: feature/short-description
Example: feature/add-trading-pair, feature/optimize-etl

CI/CD Behavior:
├─ Run full CI pipeline
├─ Build Docker images (optional)
└─ NO deployment to any environment

Developer Workflow:
1. Branch từ develop
2. Develop & test locally
3. Push code
4. Jenkins runs CI checks
5. Create Pull Request
6. Code review
7. Merge vào develop
```

#### **Develop Branch**
```
Purpose: Integration branch cho tất cả features
CI/CD Behavior:
├─ Run full CI pipeline
├─ Build & push Docker images
├─ Auto deploy to STAGING
└─ Run integration tests

Workflow:
1. Merge feature PR
2. Jenkins auto deploy to Staging
3. QA team test
4. Create release when stable
```

#### **Main Branch**
```
Purpose: Production-ready code
CI/CD Behavior:
├─ Run full CI pipeline
├─ Build & push Docker images
├─ PAUSE for manual approval
├─ Deploy to PRODUCTION (after approval)
└─ Full health & integration tests

Workflow:
1. Create PR từ develop
2. Team lead review
3. Merge to main
4. Jenkins build & wait for approval
5. Tech lead approve
6. Deploy to production
```

#### **Hotfix Branches** (`hotfix/*`)
```
Purpose: Critical bug fixes cho production
Naming: hotfix/bug-description
Example: hotfix/fix-data-loss, hotfix/memory-leak

CI/CD Behavior:
├─ Run full CI pipeline
├─ Build & push Docker images
├─ Auto deploy to STAGING first
├─ After validation → Manual approval for PROD
└─ Merge back to develop AND main

Workflow:
1. Branch từ main
2. Fix bug
3. Auto deploy to Staging
4. Quick verification
5. Approve for Production
6. Merge to main & develop
```

---

## 🏢 Environments

### 🟢 **DEV (Development)**

```yaml
Purpose: Local development & testing
URL: http://localhost:8080
Database: PostgreSQL (dev instance)
Data: Sample/Mock data
Resources: Minimal (laptop/workstation)

Configuration:
  - ENVIRONMENT: dev
  - LOG_LEVEL: DEBUG
  - AIRFLOW__CORE__LOAD_EXAMPLES: false
  - Enable debug tools
  - Relaxed security

Access:
  - All developers
  - No approval needed
  - Local only
```

### 🟡 **STAGING (Pre-production)**

```yaml
Purpose: Integration testing, QA validation
URL: http://staging.example.com
Database: PostgreSQL (staging instance)
Data: Sanitized production data
Resources: 50% of production capacity

Configuration:
  - ENVIRONMENT: staging
  - LOG_LEVEL: INFO
  - AIRFLOW__CORE__LOAD_EXAMPLES: false
  - Full monitoring enabled
  - Production-like settings

Deployment:
  - Automatic from develop branch
  - No approval required
  - Full CI/CD pipeline
  
Access:
  - Developers
  - QA team
  - Product team
  - DevOps team

Testing:
  - Integration tests
  - Performance tests
  - UAT (User Acceptance Testing)
  - Load testing
```

### 🔴 **PRODUCTION (Live)**

```yaml
Purpose: Serving real users & business operations
URL: http://prod.example.com
Database: PostgreSQL (production instance)
Data: Real production data
Resources: Full capacity + auto-scaling

Configuration:
  - ENVIRONMENT: production
  - LOG_LEVEL: WARNING
  - AIRFLOW__CORE__LOAD_EXAMPLES: false
  - Full security hardening
  - Encryption at rest & transit
  - Audit logging enabled

Deployment:
  - Manual approval required
  - Tech Lead + DevOps approval
  - Full backup before deploy
  - Blue-green deployment
  - Automatic rollback on failure
  
Access:
  - DevOps team (read-only)
  - Tech Lead (deploy approval)
  - On-call engineer

Monitoring:
  - 24/7 monitoring
  - Real-time alerting
  - PagerDuty integration
  - Performance metrics
  - Business metrics tracking
```

---

## ⏱️ Timeline & Metrics

### Pipeline Execution Time

```
┌─────────────────────────────────────────────────────────────┐
│                  PIPELINE DURATION                           │
└─────────────────────────────────────────────────────────────┘

Stage                          Time        Cumulative
───────────────────────────────────────────────────────────────
Checkout & Validation         2-3 min      2-3 min
Install Dependencies          3-5 min      5-8 min
Code Quality Checks          5-7 min      10-15 min    ← Parallel
Security Scanning            3-5 min      13-20 min    ← Parallel
Unit Tests                   5-10 min     18-30 min
Docker Build                 10-15 min    28-45 min    ← Parallel
Image Scanning               5-7 min      33-52 min
Push to Registry             3-5 min      36-57 min
─────────────────────────────────────────────────────────────
CI Phase Total              ~36-57 min
─────────────────────────────────────────────────────────────
Deploy (Staging)            5-10 min     41-67 min
Integration Tests           3-5 min      44-72 min
Health Checks              2-3 min      46-75 min
─────────────────────────────────────────────────────────────
Total (Feature Branch)      ~36-57 min   (No deploy)
Total (Develop → Staging)   ~46-75 min   (Auto deploy)
Total (Main → Production)   ~46-75 min   + Approval wait time
```

### Performance Targets

```
Metric                          Target          Critical
──────────────────────────────────────────────────────────
Pipeline Success Rate           > 95%           > 85%
Average Pipeline Time           < 60 min        < 90 min
Deployment Frequency            Daily           3x/week
Mean Time to Recovery (MTTR)    < 30 min        < 60 min
Change Failure Rate             < 5%            < 15%
Test Coverage                   > 70%           > 50%
Security Scan Pass Rate         > 90%           > 80%
```

---

## 🔔 Notification & Monitoring

### Notification Channels

```
┌─────────────────────────────────────────────────────────────┐
│                  NOTIFICATION MATRIX                         │
└─────────────────────────────────────────────────────────────┘

Event                    Priority   Channels              Recipients
─────────────────────────────────────────────────────────────────────
Pipeline Started         Info       Slack                 #deployments
Tests Passed            Info       Slack                 #deployments
Tests Failed            High       Email + Slack         Developer + Team
Code Quality Warning    Medium     Slack                 Developer
Security Alert          High       Email + Slack         Security Team + Developer
Build Failed            High       Email + Slack         Developer + DevOps
Docker Build Success    Info       Slack                 #deployments
Staging Deployed        Info       Email + Slack         #deployments + QA
Production Approval     High       Email + Slack         Tech Lead + DevOps
Production Deployed     High       Email + Slack         All + Management
Health Check Failed     Critical   Email + SMS           On-call Engineer
Rollback Triggered      Critical   Email + SMS + Call    On-call + Tech Lead
Pipeline Success        Info       Slack                 #deployments
Pipeline Failed         High       Email + Slack         Developer + DevOps
```

### Slack Notifications

```markdown
✅ **Pipeline Success**
Project: Binance Merchant Trading Flow
Build: #123
Branch: develop → staging
Duration: 52 minutes
Deployed by: @developer
Status: ✅ All tests passed, deployed to Staging
[View Build] [View Logs]

❌ **Pipeline Failed**
Project: Binance Merchant Trading Flow
Build: #124
Branch: feature/new-feature
Duration: 28 minutes
Failed at: Unit Tests
Error: 3 tests failed in test_spark_jobs.py
[View Build] [View Logs] [Rerun]

⏸️ **Approval Required**
Project: Binance Merchant Trading Flow
Build: #125
Branch: main → production
Version: v2.1.0
Changes: 15 commits, 8 files changed
Approve: @tech-lead @devops-lead
[Approve] [Reject] [View Changes]
```

### Email Templates

**Success Email:**
```
Subject: ✅ Jenkins Build Success - Binance Trading Flow #123

Build Information:
- Project: Binance Merchant Trading Flow
- Build Number: #123
- Branch: develop
- Environment: Staging
- Version: v2.0.5-a3f4b2c
- Duration: 52 minutes

Test Results:
- Unit Tests: ✅ 150 passed, 0 failed
- Code Coverage: ✅ 78%
- Security Scan: ✅ No critical issues
- Integration Tests: ✅ All passed

Deployment:
- Status: ✅ Successfully deployed to Staging
- URL: http://staging.example.com
- Health Check: ✅ All services healthy

[View Build Details] [View Test Reports] [View Logs]
```

### Monitoring Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│              JENKINS CI/CD DASHBOARD                         │
└─────────────────────────────────────────────────────────────┘

Pipeline Health                               Last 30 Days
─────────────────────────────────────────────────────────────
Success Rate:        ████████████░░ 93%       Target: > 95%
Average Duration:    ██████████░░░░ 54 min    Target: < 60 min
Failed Builds:       4 out of 58              Trend: ↓ Improving

Deployments
─────────────────────────────────────────────────────────────
Staging:    45 deploys    Last: 2 hours ago    Status: ✅ Healthy
Production: 12 deploys    Last: 3 days ago     Status: ✅ Healthy

Current Status
─────────────────────────────────────────────────────────────
Build Queue:        2 builds waiting
Active Builds:      1 in progress (Stage: Docker Build)
Last Failure:       3 days ago (Test failure)
Next Scheduled:     develop branch (waiting for commits)

Recent Activity
─────────────────────────────────────────────────────────────
#126  feature/new-api      ✅ Success    23 min ago
#125  main → production   ✅ Success    2 hours ago
#124  develop → staging   ✅ Success    5 hours ago
#123  feature/bugfix      ❌ Failed     1 day ago
```

---

## 🔄 Rollback Strategy

### Automatic Rollback Triggers

```
Rollback tự động khi:
├─ Health check failed (HTTP 500, Service unavailable)
├─ Error rate > 5% trong 5 phút
├─ API response time > 5 seconds
├─ Database connection failures
├─ Critical exceptions in logs
└─ Integration tests failed
```

### Rollback Process

```
┌─────────────────────────────────────────────────────────────┐
│                  ROLLBACK WORKFLOW                           │
└─────────────────────────────────────────────────────────────┘

1. Detect Failure (Automatic or Manual)
   ├─ Health check monitoring
   ├─ Performance metrics
   └─ Manual trigger by on-call engineer

2. Initiate Rollback (30 seconds)
   ├─ Send critical alert
   ├─ Lock deployment queue
   └─ Start rollback procedure

3. Stop Current Services (1 minute)
   ├─ Graceful shutdown of Airflow workers
   ├─ Stop accepting new requests
   ├─ Drain active connections
   └─ Stop containers

4. Restore Database (2-3 minutes)
   ├─ Identify last good backup
   ├─ Stop write operations
   ├─ Restore database from backup
   └─ Verify data integrity

5. Deploy Previous Version (2-3 minutes)
   ├─ Fetch previous Docker images
   ├─ Update docker-compose configuration
   ├─ Start services with old version
   └─ Wait for services to be ready

6. Verify Rollback (2-3 minutes)
   ├─ Run health checks
   ├─ Verify API endpoints
   ├─ Check error rates
   ├─ Monitor performance
   └─ Confirm data consistency

7. Cleanup & Alert (1 minute)
   ├─ Update deployment status
   ├─ Unlock deployment queue
   ├─ Send notification
   ├─ Create incident ticket
   └─ Schedule post-mortem

Total Rollback Time: 8-12 minutes
```

### Manual Rollback

```bash
# Via Jenkins UI
1. Go to "Rollback Job"
2. Click "Build with Parameters"
3. Select environment (staging/production)
4. Select target version to rollback to
5. Click "Build"

# Via Command Line
jenkins-cli rollback \
  --environment production \
  --to-version v2.0.4 \
  --reason "Critical bug in payment processing"
```

### Rollback Verification Checklist

```
☐ All services are running
☐ Health checks are passing
☐ Database is accessible
☐ No error spikes in logs
☐ API response times normal
☐ Airflow DAGs are scheduled
☐ Workers are processing tasks
☐ Data pipeline is running
☐ Metrics dashboard shows normal patterns
☐ Alert channels notified of rollback
```

---

## 🛠️ Setup Instructions

### Prerequisites

```bash
# System Requirements
- Jenkins Server (version 2.400+)
- Docker (version 24.0+)
- Docker Compose (version 2.20+)
- Python 3.10+
- Git 2.30+

# Resource Requirements
- CPU: 4+ cores
- RAM: 8GB+ (16GB recommended)
- Disk: 100GB+ free space
- Network: Stable internet connection
```

### Step 1: Install Jenkins Plugins

```groovy
// Navigate to: Manage Jenkins → Manage Plugins

Required Plugins:
☐ Pipeline
☐ Git Plugin
☐ Docker Pipeline
☐ Email Extension Plugin
☐ Slack Notification Plugin
☐ JUnit Plugin
☐ HTML Publisher Plugin
☐ Credentials Binding Plugin
☐ Parameterized Trigger Plugin
☐ Blue Ocean (optional, for better UI)
```

### Step 2: Configure Credentials

```bash
# Navigate to: Manage Jenkins → Manage Credentials

Add the following credentials:

1. GitHub Credentials (github-credentials)
   Type: Username with password / SSH Key
   ID: github-credentials
   Description: GitHub Access Token

2. Docker Registry Credentials (docker-credentials-id)
   Type: Username with password
   ID: docker-credentials-id
   Username: <your-docker-username>
   Password: <your-docker-token>

3. AWS Credentials (aws-credentials-id) - Optional
   Type: AWS Credentials
   ID: aws-credentials-id
   Access Key: <your-aws-access-key>
   Secret Key: <your-aws-secret-key>

4. Email Credentials
   Type: Username with password
   ID: email-credentials
   Username: <smtp-username>
   Password: <smtp-password>
```

### Step 3: Create Jenkins Pipeline Job

```bash
1. Click "New Item"
2. Enter name: "binance-merchant-trading-flow"
3. Select "Pipeline"
4. Click "OK"

5. Configure:
   General:
   ☐ GitHub project: <your-github-repo-url>
   ☐ This project is parameterized
   
   Build Triggers:
   ☐ GitHub hook trigger for GITScm polling
   ☐ Poll SCM: H/5 * * * * (every 5 minutes)
   
   Pipeline:
   ☐ Definition: Pipeline script from SCM
   ☐ SCM: Git
   ☐ Repository URL: <your-repo-url>
   ☐ Credentials: github-credentials
   ☐ Branch: */main
   ☐ Script Path: Jenkinsfile

6. Save
```

### Step 4: Configure GitHub Webhook

```bash
# In GitHub Repository Settings:

1. Go to Settings → Webhooks
2. Click "Add webhook"
3. Payload URL: http://<jenkins-server>/github-webhook/
4. Content type: application/json
5. Secret: <optional-secret>
6. Events: 
   ☑ Push
   ☑ Pull request
7. Click "Add webhook"
```

### Step 5: Configure Email Notifications

```bash
# Navigate to: Manage Jenkins → Configure System

Email Notification:
- SMTP server: smtp.gmail.com
- SMTP port: 587
- Use TLS: ☑
- SMTP Username: <your-email>
- SMTP Password: <your-password>

Extended E-mail Notification:
- SMTP server: smtp.gmail.com
- Default Recipients: team@example.com
- Reply-To Address: noreply@example.com
- Default Content Type: HTML (text/html)
```

### Step 6: Configure Slack Notifications (Optional)

```bash
# Navigate to: Manage Jenkins → Configure System

Slack:
- Workspace: <your-workspace>
- Credential: <slack-token>
- Default Channel: #deployments
- Test Connection: Should return "Success"
```

### Step 7: Setup Environment Variables

```bash
# Create .env files in project root

.env.dev:
ENVIRONMENT=dev
DOCKER_REGISTRY=docker.io/<your-username>
LOG_LEVEL=DEBUG

.env.staging:
ENVIRONMENT=staging
DOCKER_REGISTRY=docker.io/<your-username>
LOG_LEVEL=INFO

.env.production:
ENVIRONMENT=production
DOCKER_REGISTRY=docker.io/<your-username>
LOG_LEVEL=WARNING
```

### Step 8: Test Pipeline

```bash
# Manual test run:
1. Go to Jenkins job
2. Click "Build Now"
3. Monitor console output
4. Verify all stages pass

# Expected result:
✅ All stages green
✅ Docker images built and pushed
✅ No errors in logs
```

---

## 🐛 Troubleshooting

### Common Issues & Solutions

#### Issue 1: Docker Build Fails

```
Error: "Cannot connect to the Docker daemon"

Solution:
1. Verify Docker service is running:
   sudo systemctl status docker
   
2. Add Jenkins user to docker group:
   sudo usermod -aG docker jenkins
   sudo systemctl restart jenkins
   
3. Check Docker socket permissions:
   ls -l /var/run/docker.sock
   sudo chmod 666 /var/run/docker.sock
```

#### Issue 2: Tests Fail in CI but Pass Locally

```
Error: Tests pass on local machine but fail in Jenkins

Solution:
1. Check Python version consistency:
   - Local: python --version
   - Jenkins: Verify in build logs
   
2. Check environment variables:
   - Ensure .env files are loaded correctly
   - Set AIRFLOW__CORE__UNIT_TEST_MODE=True
   
3. Check dependencies:
   pip freeze > local-requirements.txt
   # Compare with requirements.txt
   
4. Run tests in clean environment:
   python -m venv test-env
   source test-env/bin/activate
   pip install -r requirements.txt
   pytest
```

#### Issue 3: Deployment Hangs

```
Error: Deployment stage hangs and eventually times out

Solution:
1. Check Docker Compose logs:
   docker-compose logs -f
   
2. Verify ports are not in use:
   netstat -tulpn | grep 8080
   
3. Check resource availability:
   df -h  # Disk space
   free -m  # Memory
   
4. Manually stop and restart:
   docker-compose down -v
   docker system prune -f
   docker-compose up -d
```

#### Issue 4: Health Checks Fail

```
Error: Services deployed but health checks fail

Solution:
1. Wait longer for services to initialize:
   # Increase wait time in Jenkinsfile
   sleep 60  # Instead of 30
   
2. Check service logs:
   docker-compose logs airflow-apiserver
   docker-compose logs postgres
   
3. Verify database migrations:
   docker-compose exec airflow-apiserver airflow db check
   
4. Test health endpoint manually:
   curl -v http://localhost:8080/health
```

#### Issue 5: Permission Denied Errors

```
Error: "Permission denied" when accessing files or directories

Solution:
1. Fix file permissions:
   chmod +x scripts/*.sh
   
2. Fix directory ownership:
   sudo chown -R jenkins:jenkins /var/jenkins_home/workspace/
   
3. Update AIRFLOW_UID in .env:
   echo "AIRFLOW_UID=$(id -u)" >> .env
```

#### Issue 6: Git Authentication Fails

```
Error: "Authentication failed" when cloning repository

Solution:
1. Update GitHub credentials in Jenkins
2. Use Personal Access Token instead of password
3. Verify SSH key is added to GitHub:
   ssh -T git@github.com
4. Update repository URL to use HTTPS or SSH correctly
```

#### Issue 7: Out of Memory Errors

```
Error: "Out of memory" during build or tests

Solution:
1. Increase Docker memory limit:
   # Edit /etc/docker/daemon.json
   {
     "default-shm-size": "2g"
   }
   
2. Limit parallel builds in Jenkins:
   # Manage Jenkins → Configure System
   # # of executors: 2 (reduce from higher number)
   
3. Optimize pytest execution:
   pytest -n 2  # Limit parallel workers
   pytest --maxfail=1  # Stop on first failure
```

#### Issue 8: Slow Pipeline Execution

```
Issue: Pipeline takes too long to complete

Optimization:
1. Enable parallel stages:
   # Already implemented for code quality & security
   
2. Use Docker layer caching:
   docker build --cache-from <previous-image>
   
3. Optimize test execution:
   pytest -n auto --dist loadscope
   
4. Use faster mirror for pip:
   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple
   
5. Archive artifacts selectively:
   # Only keep important reports, not all files
```

### Getting Help

```
📧 Email: devops-team@example.com
💬 Slack: #jenkins-support
📚 Documentation: https://docs.example.com/cicd
🐛 Issue Tracker: https://jira.example.com/CICD
```

---

## 📚 Additional Resources

### Documentation

- [Jenkins Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Docker Multi-Stage Builds](https://docs.docker.com/develop/develop-images/multistage-build/)
- [Apache Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

### Monitoring & Logs

```bash
# View Jenkins build logs
http://<jenkins-server>/job/binance-merchant-trading-flow/<build-number>/console

# View Docker logs
docker-compose logs -f --tail=100

# View Airflow logs
docker-compose exec airflow-apiserver cat /opt/airflow/logs/scheduler/latest/

# View system resources
htop
docker stats
```

### Useful Commands

```bash
# Trigger build from CLI
jenkins-cli build binance-merchant-trading-flow \
  -p DEPLOY_ENV=staging \
  -p RUN_TESTS=true

# Check pipeline status
jenkins-cli get-job binance-merchant-trading-flow

# Abort running build
jenkins-cli stop-build binance-merchant-trading-flow <build-number>

# List recent builds
jenkins-cli list-builds binance-merchant-trading-flow

# Download build logs
jenkins-cli console binance-merchant-trading-flow > build.log
```

---

## 🎯 Best Practices

### Development

```
✅ DO:
- Write tests for new features
- Run tests locally before pushing
- Use feature branches for development
- Keep commits atomic and meaningful
- Update documentation when changing behavior

❌ DON'T:
- Push directly to main branch
- Skip code review process
- Commit large binary files
- Hardcode credentials in code
- Disable CI checks to "save time"
```

### Deployment

```
✅ DO:
- Deploy to staging first
- Verify in staging before production
- Use semantic versioning
- Tag releases in Git
- Monitor after deployment
- Have rollback plan ready

❌ DON'T:
- Deploy on Friday afternoon
- Deploy without testing
- Deploy multiple changes at once
- Skip approval for production
- Deploy without notification
```

### Maintenance

```
✅ DO:
- Regular Jenkins plugin updates
- Clean up old builds (keep last 30)
- Monitor disk space
- Review failed builds
- Update dependencies regularly
- Conduct post-mortem for failures

❌ DON'T:
- Ignore security warnings
- Let disk space fill up
- Keep failing builds without investigation
- Use outdated dependencies
- Skip maintenance windows
```

---

## 📊 Metrics & KPIs

### Key Performance Indicators

```
Metric                          Current    Target      Status
──────────────────────────────────────────────────────────────
Deployment Frequency            12/month   15/month    📈 Good
Lead Time for Changes           2 days     1 day       📈 Good
Mean Time to Recovery (MTTR)    25 min     30 min      ✅ Excellent
Change Failure Rate             3%         5%          ✅ Excellent
Pipeline Success Rate           93%        95%         📈 Good
Average Build Time              54 min     60 min      ✅ Excellent
Test Coverage                   78%        70%         ✅ Excellent
Security Scan Pass Rate         91%        90%         ✅ Excellent
```

---

## 🔐 Security Considerations

### Security Checklist

```
☑ Credentials stored in Jenkins credentials store
☑ No hardcoded secrets in code
☑ Docker images scanned for vulnerabilities
☑ Dependencies checked for known CVEs
☑ Code scanned with Bandit for security issues
☑ HTTPS enforced for all communications
☑ Access controlled with RBAC
☑ Audit logs enabled
☑ Secrets encrypted at rest
☑ Regular security audits scheduled
```

---

## 📞 Support & Contact

```
Team                Role                    Contact
────────────────────────────────────────────────────────────
DevOps Team        Pipeline maintenance     devops@example.com
Security Team      Security review          security@example.com
QA Team            Test validation          qa@example.com
On-Call Engineer   24/7 production support  oncall@example.com

Emergency: +1-XXX-XXX-XXXX (PagerDuty)
```

---

**Last Updated**: November 2024  
**Version**: 1.0  
**Maintained by**: DevOps Team


