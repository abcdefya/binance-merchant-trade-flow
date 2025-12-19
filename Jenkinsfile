pipeline {
  agent any

  environment {
    GCR_REGION = "asia-southeast1"
    GCR_HOST   = "asia-southeast1-docker.pkg.dev"
    GCR_REPO   = "docker-images"
  }

  stages {

    /* ============================
     * Clean
     * ============================ */
    stage('Clean Workspace') {
      steps {
        cleanWs()
      }
    }

    /* ============================
     * Checkout Source
     * ============================ */
    stage('Git Checkout') {
      steps {
        git branch: 'gcp_deployment',
            url: 'https://github.com/abcdefya/binance-merchant-trade-flow.git',
            credentialsId: 'github-key'
      }
    }

    /* =====================================================
     * Batch Processing
     * ===================================================== */
    stage('Batch: Build & Deploy') {
      when {
        changeset "dockerfiles/batch-processing/**"
      }

      environment {
        IMAGE_NAME = "batch-app"
      }

      stages {

        stage('Build Batch Image') {
          steps {
            sh '''
              docker build \
                -f dockerfiles/batch-processing/Dockerfile \
                -t ${IMAGE_NAME}:latest .
            '''
          }
        }

        stage('Auth GCP & Docker (Batch)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                which gcloud
                gcloud --version

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker ${GCR_HOST} -q
              '''
            }
          }
        }

        stage('Push Batch Image') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                IMAGE_URI=${GCR_HOST}/${GCP_PROJECT}/${GCR_REPO}/${IMAGE_NAME}:latest
                docker tag ${IMAGE_NAME}:latest ${IMAGE_URI}
                docker push ${IMAGE_URI}
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * Streaming Processing (TAG = GIT COMMIT)
     * ===================================================== */
    stage('Streaming: Build & Deploy') {
      when {
        changeset "dockerfiles/streaming-processing/**"
      }

      environment {
        IMAGE_NAME = "stream-app"
      }

      stages {

        stage('Build Streaming Image') {
          steps {
            sh '''
              docker build \
                -f dockerfiles/streaming-processing/Dockerfile \
                -t ${IMAGE_NAME}:latest .
            '''
          }
        }

        stage('Auth GCP & Docker (Streaming)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                which gcloud
                gcloud --version

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker ${GCR_HOST} -q
              '''
            }
          }
        }

        stage('Push Streaming Image (git commit)') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                SHORT_COMMIT=$(echo "$GIT_COMMIT" | cut -c1-7)
                IMAGE_TAG=git-${SHORT_COMMIT}

                IMAGE_URI=${GCR_HOST}/${GCP_PROJECT}/${GCR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}

                docker tag ${IMAGE_NAME}:latest ${IMAGE_URI}
                docker push ${IMAGE_URI}
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * Ingestion Processing
     * ===================================================== */
    stage('Ingestion: Build & Deploy') {
      when {
        changeset "dockerfiles/ingestion/**"
      }

      environment {
        IMAGE_NAME = "ingestion-app"
      }

      stages {

        stage('Build Ingestion Image') {
          steps {
            sh '''
              docker build \
                -f dockerfiles/ingestion/Dockerfile \
                -t ${IMAGE_NAME}:latest .
            '''
          }
        }

        stage('Auth GCP & Docker (Ingestion)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                which gcloud
                gcloud --version

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker ${GCR_HOST} -q
              '''
            }
          }
        }

        stage('Push Ingestion Image') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                IMAGE_URI=${GCR_HOST}/${GCP_PROJECT}/${GCR_REPO}/${IMAGE_NAME}:latest
                docker tag ${IMAGE_NAME}:latest ${IMAGE_URI}
                docker push ${IMAGE_URI}
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * No Docker Changes
     * ===================================================== */
    stage('No Docker Changes Detected') {
      when {
        allOf {
          not { changeset "dockerfiles/batch-processing/**" }
          not { changeset "dockerfiles/streaming-processing/**" }
          not { changeset "dockerfiles/ingestion/**" }
        }
      }
      steps {
        echo "No dockerfile changes detected — skip build & push."
      }
    }
  }

  post {
    always {
      echo "Pipeline finished for commit ${env.GIT_COMMIT}"
    }
    success {
      echo "✅ Build & push to Artifact Registry succeeded"
    }
    failure {
      echo "❌ Build or push failed"
    }
  }
}
