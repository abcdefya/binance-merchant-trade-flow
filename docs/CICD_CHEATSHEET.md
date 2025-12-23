# 🚀 CI/CD Pipeline Cheatsheet

> **Quick reference cho Jenkins CI/CD Pipeline**

---

## ⚡ TL;DR

```bash
feature/* → Test only (30 min)
develop   → Auto deploy to Staging (60 min)
main      → Manual approve → Production (70 min)
```

---

## 🌿 Branching Quick Reference

| Branch Pattern | Deploy To | Time | Auto Deploy | Approval |
|----------------|-----------|------|-------------|----------|
| `feature/*` | ❌ None | 30-45 min | ❌ | ❌ |
| `develop` | 🟡 Staging | 50-70 min | ✅ | ❌ |
| `main` | 🔴 Production | 60-80 min | ✅ | ✅ **Required** |
| `hotfix/*` | 🟡→🔴 Both | 70-90 min | ✅→⏸️ | ✅ **For Prod** |

---

## 📝 Developer Workflow

### Creating a Feature

```bash
# 1. Start from develop
git checkout develop
git pull origin develop

# 2. Create feature branch
git checkout -b feature/add-new-endpoint

# 3. Make changes
# ... code ...

# 4. Test locally
pytest tests/
flake8 src/
black src/

# 5. Commit
git add .
git commit -m "feat: add new trading endpoint"

# 6. Push (triggers CI)
git push origin feature/add-new-endpoint
```

**What happens**: Jenkins runs tests, quality checks, builds Docker (30-45 min)

### Deploying to Staging

```bash
# 1. Create PR: feature → develop
# 2. Code review
# 3. Merge PR
```

**What happens**: Jenkins auto deploys to Staging (50-70 min)

### Deploying to Production

```bash
# 1. Verify Staging works
# 2. Create PR: develop → main
# 3. Team lead reviews
# 4. Merge PR
# 5. Jenkins builds and waits
# 6. Tech lead approves via Jenkins UI
```

**What happens**: Blue-green deployment to Production (60-80 min)

---

## 🧪 Pre-Push Checklist

```bash
☐ Tests pass locally:        pytest tests/
☐ No linting errors:          flake8 src/ dags/
☐ Code formatted:             black --check src/ dags/
☐ Imports sorted:             isort --check src/ dags/
☐ No security issues:         bandit -r src/
☐ Docker builds:              docker-compose build
☐ Commit message format:      type: description
```

### Commit Message Format

```
feat: add new feature
fix: fix bug in data processing
docs: update documentation
test: add unit tests
refactor: refactor code structure
perf: improve performance
chore: update dependencies
```

---

## 🔍 Pipeline Stages

| # | Stage | Time | Fail Action |
|---|-------|------|-------------|
| 1 | Checkout | 2-3 min | ❌ Stop |
| 2 | Install Deps | 3-5 min | ❌ Stop |
| 3 | Code Quality | 5-7 min | ⚠️ Warn |
| 4 | Security Scan | 3-5 min | ⚠️ Warn |
| 5 | Unit Tests | 5-10 min | ❌ Stop |
| 6 | Build Docker | 10-15 min | ❌ Stop |
| 7 | Image Scan | 5-7 min | ⚠️ Warn |
| 8 | Push Registry | 3-5 min | ❌ Stop |
| 9 | Deploy | 5-10 min | 🔄 Rollback |
| 10 | Integration Tests | 3-5 min | 🔄 Rollback |
| 11 | Health Checks | 2-3 min | 🔄 Rollback |

---

## 🚦 Status Icons

| Icon | Meaning |
|------|---------|
| 🟢 | Success / Healthy |
| 🟡 | Warning / In Progress |
| 🔴 | Failed / Error |
| ⏸️ | Waiting for Approval |
| 🔄 | Rolling Back |
| ⚠️ | Alert / Attention Needed |

---

## 📱 Jenkins Quick Commands

### View Build Status

```bash
# Open Jenkins
https://jenkins.example.com/job/binance-merchant-trading-flow/

# Via CLI
jenkins-cli get-job binance-merchant-trading-flow
```

### Trigger Manual Build

```bash
# Via UI
Jenkins → Job → Build with Parameters

# Via CLI
jenkins-cli build binance-merchant-trading-flow \
  -p DEPLOY_ENV=staging \
  -p RUN_TESTS=true
```

### View Logs

```bash
# Via UI
Jenkins → Job → Build #123 → Console Output

# Via CLI
jenkins-cli console binance-merchant-trading-flow 123
```

### Approve Production Deploy

```bash
# Via UI
Jenkins → Job → Build #123 → Input Requested → Approve

# You'll receive email + Slack notification
```

---

## 🐳 Docker Quick Commands

### Local Development

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Debugging

```bash
# Check service status
docker-compose ps

# Enter container
docker-compose exec airflow-apiserver bash

# View specific service logs
docker-compose logs -f airflow-scheduler

# Restart service
docker-compose restart airflow-worker
```

### Cleanup

```bash
# Remove all containers
docker-compose down -v

# Clean up images
docker system prune -f

# Clean up volumes
docker volume prune -f
```

---

## 🔍 Health Check Commands

### Quick Health Check

```bash
# Airflow Web UI
curl http://localhost:8080/health

# Airflow Scheduler
docker-compose exec airflow-scheduler \
  airflow jobs check --job-type SchedulerJob

# PostgreSQL
docker-compose exec postgres pg_isready -U airflow

# Redis
docker-compose exec redis redis-cli ping
```

### Full Health Check Script

```bash
# Run health check script
bash scripts/health-check.sh
```

---

## 🔔 Where to Get Notifications

### Slack Channels

- `#deployments` - All deployment events
- `#ci-alerts` - Build failures & errors
- `#security-alerts` - Security scan results

### Email

- Developer gets: Build failures, test failures
- Team gets: Staging deployments, production approvals
- On-call gets: Critical alerts, rollbacks

---

## 🐛 Troubleshooting Quick Fixes

### Build Fails - Tests

```bash
# Problem: Tests pass locally, fail in CI
# Solution:
1. Check Python version matches
2. Run in clean environment:
   python -m venv fresh-env
   source fresh-env/bin/activate
   pip install -r requirements.txt
   pytest
```

### Build Fails - Docker

```bash
# Problem: Docker build fails
# Solution:
sudo systemctl restart docker
docker system prune -f
docker-compose build --no-cache
```

### Deployment Hangs

```bash
# Problem: Deployment stuck
# Solution:
docker-compose logs -f  # Check what's wrong
docker-compose down -v  # Hard reset
docker-compose up -d    # Start fresh
```

### Health Check Fails

```bash
# Problem: Services up but health check fails
# Solution:
1. Wait 60 seconds (services need time)
2. Check logs: docker-compose logs -f
3. Manual test: curl http://localhost:8080/health
4. Restart: docker-compose restart
```

### Permission Denied

```bash
# Problem: Permission errors
# Solution:
chmod +x scripts/*.sh
echo "AIRFLOW_UID=$(id -u)" >> .env
docker-compose down -v
docker-compose up -d
```

---

## 🔙 Rollback Quick Guide

### Automatic Rollback

Triggers automatically when:
- Health checks fail
- Error rate > 5%
- Integration tests fail

### Manual Rollback

```bash
# Via Jenkins UI
1. Go to "Rollback Job"
2. Select environment: production
3. Select version to rollback to
4. Click "Build"

# Via Script
bash scripts/rollback.sh
```

**Time to rollback**: 8-12 minutes

---

## 📊 Key Metrics to Watch

```
Metric                 Current   Target    Status
─────────────────────────────────────────────────
Success Rate           93%       >95%      📈
Build Time             54 min    <60 min   ✅
Test Coverage          78%       >70%      ✅
MTTR                   25 min    <30 min   ✅
Deploy Frequency       12/mo     15/mo     📈
Change Fail Rate       3%        <5%       ✅
```

---

## 🔗 Quick Links

| Resource | URL |
|----------|-----|
| Jenkins | https://jenkins.example.com |
| Staging | http://staging.example.com |
| Production | http://prod.example.com |
| Grafana | http://grafana.example.com |
| GitHub | https://github.com/your-org/repo |

---

## 📞 Emergency Contacts

```
Issue Type          Contact              Channel
──────────────────────────────────────────────────
Build Failure       DevOps Team          #jenkins-support
Test Failure        Dev Team             #dev-team
Deploy Issue        DevOps Team          #devops-team
Security Alert      Security Team        #security-team
Production Down     On-Call Engineer     Phone + PagerDuty
                    +1-XXX-XXX-XXXX
```

---

## 🎯 Best Practices

### DO ✅

- Write tests before pushing
- Run linters locally
- Use meaningful commit messages
- Create small, focused PRs
- Test in Staging before Production
- Monitor after deployment
- Tag releases in Git

### DON'T ❌

- Push directly to main
- Skip code review
- Deploy on Friday evening
- Deploy without testing
- Ignore CI failures
- Hardcode secrets
- Commit large files

---

## 📚 Full Documentation

For detailed information, see:

- 📖 [Full CI/CD Pipeline Guide](./CICD_PIPELINE.md)
- ⚡ [Quick Start Guide](./CICD_QUICKSTART.md)
- 📊 [Flow Diagrams](./cicd-flow-diagram.md)

---

## 💡 Pro Tips

```
1. Set up git hooks for pre-commit checks
2. Use Jenkins Blue Ocean for better UI
3. Enable desktop notifications
4. Bookmark Jenkins job URL
5. Join Slack channels for alerts
6. Use Jenkins CLI for automation
7. Test rollback procedure regularly
8. Keep local environment updated
```

---

**Quick Help**: Slack `#jenkins-support` | Email: `devops@example.com`

**Last Updated**: November 2024


