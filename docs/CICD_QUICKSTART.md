# 🚀 CI/CD Pipeline - Quick Reference

> **Quick guide cho việc sử dụng Jenkins CI/CD Pipeline**

## 📋 TL;DR (Too Long; Didn't Read)

```
Push Code → Jenkins Auto Run → Test → Build → Deploy
├─ Feature branch → Test only (20-30 min)
├─ Develop branch → Auto deploy to Staging (50-70 min)
└─ Main branch → Manual approval → Production (60+ min)
```

---

## 🎯 Quy Trình Cơ Bản

### 1. Developer Workflow

```bash
# 1. Tạo feature branch
git checkout develop
git pull
git checkout -b feature/your-feature-name

# 2. Code & test locally
# ... write code ...
pytest tests/

# 3. Commit & push
git add .
git commit -m "feat: your feature description"
git push origin feature/your-feature-name

# 4. Jenkins tự động chạy CI
# ✓ Tests
# ✓ Code quality
# ✓ Security scan
# ✗ No deployment

# 5. Tạo Pull Request
# - Code review
# - CI checks must pass
# - Merge vào develop

# 6. Develop auto deploy to Staging
# - Jenkins auto deploy
# - QA team test
```

### 2. Release to Production

```bash
# 1. Verify staging works well
# 2. Create PR: develop → main
# 3. Team lead review & approve PR
# 4. Merge to main
# 5. Jenkins build & wait for approval
# 6. Tech lead approve deployment
# 7. Auto deploy to production
# 8. Monitor for 30 minutes
```

---

## ⏱️ Timeline Reference

```
Pipeline Stage          Feature     Develop     Main
──────────────────────────────────────────────────────
CI Tests               ✓ 20-30 min ✓ 20-30 min ✓ 20-30 min
Build Docker          ✓ 10-15 min ✓ 10-15 min ✓ 10-15 min
Deploy Staging        ✗ Skip      ✓ 10 min    ✗ Skip
Deploy Production     ✗ Skip      ✗ Skip      ⏸️ Approval + 10 min
──────────────────────────────────────────────────────
Total                 ~30-45 min  ~50-70 min  ~60+ min
```

---

## 🌿 Branch Strategy

```
feature/xxx → develop → staging → main → production
   (test)     (auto)    (test)    (manual) (live)
```

| Branch | Deploy To | Auto/Manual | Approval |
|--------|-----------|-------------|----------|
| `feature/*` | None | N/A | No |
| `develop` | Staging | Auto | No |
| `main` | Production | Auto | **Yes** |
| `hotfix/*` | Staging → Prod | Auto → Manual | **Yes for Prod** |

---

## ✅ Pre-Push Checklist

```bash
# Run locally trước khi push:

☐ pytest tests/                          # Tests pass
☐ flake8 src/ dags/                      # No linting errors
☐ black --check src/ dags/               # Code formatted
☐ isort --check src/ dags/               # Imports sorted
☐ bandit -r src/                         # No security issues
☐ docker-compose up -d                   # Local deployment works
☐ # Commit message follows convention
```

---

## 🔔 Notifications

### Slack Channels

- `#deployments` - All deployment notifications
- `#ci-alerts` - Failed builds & errors
- `#security-alerts` - Security scan results

### Email Notifications

- **Success**: Sent to team channel only
- **Failure**: Sent to **developer + team**
- **Production Deploy**: Sent to **all + management**
- **Critical Alert**: Sent to **on-call engineer**

---

## 🛠️ Quick Commands

### Jenkins CLI

```bash
# Trigger build
jenkins-cli build binance-merchant-trading-flow -p DEPLOY_ENV=staging

# Check status
jenkins-cli get-job binance-merchant-trading-flow

# View logs
jenkins-cli console binance-merchant-trading-flow 125

# Abort build
jenkins-cli stop-build binance-merchant-trading-flow 125
```

### Docker Commands

```bash
# View logs
docker-compose logs -f --tail=100

# Health check
curl http://localhost:8080/health

# Restart services
docker-compose restart

# Clean up
docker-compose down -v
docker system prune -f
```

### Debug Commands

```bash
# Check Airflow
docker-compose exec airflow-apiserver airflow version
docker-compose exec airflow-apiserver airflow db check

# Check database
docker-compose exec postgres pg_isready -U airflow

# Check Redis
docker-compose exec redis redis-cli ping

# View service status
docker-compose ps
```

---

## 🐛 Common Issues

### Build Fails at Tests

```bash
Problem: Tests pass locally but fail in CI

Fix:
1. Check Python version matches
2. Verify environment variables
3. Check .env files are loaded
4. Run in clean virtual environment
```

### Deployment Hangs

```bash
Problem: Deployment stuck at "Starting services"

Fix:
1. Check Docker logs: docker-compose logs -f
2. Verify ports not in use: netstat -tulpn | grep 8080
3. Check disk space: df -h
4. Restart Docker: sudo systemctl restart docker
```

### Permission Denied

```bash
Problem: Permission denied errors

Fix:
1. chmod +x scripts/*.sh
2. sudo chown -R jenkins:jenkins /var/jenkins_home/
3. echo "AIRFLOW_UID=$(id -u)" >> .env
```

### Health Checks Fail

```bash
Problem: Services up but health checks fail

Fix:
1. Wait longer: sleep 60
2. Check service logs
3. Test manually: curl http://localhost:8080/health
4. Verify migrations: airflow db check
```

---

## 📊 Pipeline Success Criteria

```
Stage                Pass Criteria              Action if Fail
────────────────────────────────────────────────────────────────
Unit Tests          All pass                   ❌ STOP pipeline
Code Coverage       > 70%                      ⚠️ Warning
Code Quality        Pylint > 7.0               ⚠️ Warning
Security Scan       No CRITICAL issues         ⚠️ Warning
Docker Build        Build succeeds             ❌ STOP pipeline
Integration Tests   All pass                   🔄 Rollback
Health Checks       All services healthy       🔄 Rollback
```

---

## 🚨 Emergency Procedures

### Rollback Production

```bash
# Option 1: Via Jenkins
1. Go to "Rollback Job"
2. Select environment: production
3. Select version to rollback to
4. Click "Build"

# Option 2: Manual
cd /path/to/project
bash scripts/rollback.sh
```

### Pause Deployments

```bash
# Stop all queued builds
jenkins-cli quiet-down

# Resume deployments
jenkins-cli cancel-quiet-down
```

### Emergency Contact

```
🔴 Critical Issues:
   - On-Call Engineer: oncall@example.com
   - Phone: +1-XXX-XXX-XXXX (PagerDuty)

🟡 Build Issues:
   - DevOps Team: devops@example.com
   - Slack: #jenkins-support
```

---

## 📱 Mobile Access

### Jenkins Mobile App

```
Download: Jenkins Mobile (iOS/Android)
Server: https://jenkins.example.com
API Token: Generate from Jenkins → User → Configure
```

### Quick Actions from Phone

- View build status
- Approve deployments
- Trigger rollback
- View logs
- Get notifications

---

## 🔗 Quick Links

- 📚 [Full CI/CD Documentation](./CICD_PIPELINE.md)
- 🏗️ [Architecture Diagram](./architecture/)
- 🧪 [Testing Guide](./TESTING.md)
- 🐳 [Docker Setup](./DOCKER.md)
- 🔐 [Security Guide](./SECURITY.md)

---

## 💡 Pro Tips

```
✨ Optimize your workflow:

1. Use git hooks to run tests locally before push
2. Set up IDE integration with Jenkins
3. Use Jenkins Blue Ocean for better visualization
4. Enable desktop notifications for build status
5. Bookmark Jenkins job URL for quick access
6. Set up Slack bot for quick commands
7. Use Jenkins CLI for automation
8. Create custom views for your team
```

---

## 📞 Support

```
Question?              Contact
─────────────────────────────────────────
Pipeline issues       #jenkins-support
Test failures         #dev-team
Deployment help       #devops-team
Security concerns     #security-team
Emergency             oncall@example.com
```

---

**Need detailed info?** → Read [Full CI/CD Pipeline Documentation](./CICD_PIPELINE.md)

**Last Updated**: November 2024  
**Quick Help**: Slack `#jenkins-support`


