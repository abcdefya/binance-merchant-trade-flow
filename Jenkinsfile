pipeline {
  agent any

  environment {
    GAR_HOST = "asia-southeast1-docker.pkg.dev"
    GAR_REPO = "docker-images"
  }

  stages {

    /* ===============================
     * CLEAN
     * =============================== */
    stage('Clean Workspace') {
      steps {
        cleanWs()
      }
    }

    /* ===============================
     * CHECKOUT
     * =============================== */
    stage('Git Checkout') {
      steps {
        git branch: 'gcp_deployment',
            url: 'https://github.com/abcdefya/binance-merchant-trade-flow.git',
            credentialsId: 'github-key'
      }
    }

    /* =====================================================
     * BATCH PROCESSING
     * ===================================================== */
    stage('Batch: Build & Deploy') {
      when {
        changeset "dockerfiles/batch-processing/**"
      }
      stages {

        stage('Build Batch Image') {
          steps {
            sh '''
              set -e
              docker build \
                -f dockerfiles/batch-processing/Dockerfile \
                -t batch-app:latest .
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
                set -e
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker asia-southeast1-docker.pkg.dev -q
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
                set -e
                IMAGE=${GAR_HOST}/${GCP_PROJECT}/${GAR_REPO}/batch-app:latest
                docker tag batch-app:latest $IMAGE
                docker push $IMAGE
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * STREAMING PROCESSING (TAG = GIT COMMIT)
     * ===================================================== */
    stage('Streaming: Build & Deploy') {
      when {
        changeset "dockerfiles/streaming-processing/**"
      }
      stages {

        stage('Build Streaming Image') {
          steps {
            sh '''
              set -e
              docker build \
                -f dockerfiles/streaming-processing/Dockerfile \
                -t stream-app:latest .
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
                set -e
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker asia-southeast1-docker.pkg.dev -q
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
                set -e
                SHORT_COMMIT=$(echo "$GIT_COMMIT" | cut -c1-7)
                TAG=git-${SHORT_COMMIT}

                IMAGE=${GAR_HOST}/${GCP_PROJECT}/${GAR_REPO}/stream-app:${TAG}
                docker tag stream-app:latest $IMAGE
                docker push $IMAGE
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * INGESTION PROCESSING
     * ===================================================== */
    stage('Ingestion: Build & Deploy') {
      when {
        changeset "dockerfiles/ingestion/**"
      }
      stages {

        stage('Build Ingestion Image') {
          steps {
            sh '''
              set -e
              docker build \
                -f dockerfiles/ingestion/Dockerfile \
                -t ingestion-app:latest .
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
                set -e
                export PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

                gcloud auth activate-service-account --key-file="$GCP_KEY"
                gcloud config set project "$GCP_PROJECT"
                gcloud auth configure-docker asia-southeast1-docker.pkg.dev -q
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
                set -e
                IMAGE=${GAR_HOST}/${GCP_PROJECT}/${GAR_REPO}/ingestion-app:latest
                docker tag ingestion-app:latest $IMAGE
                docker push $IMAGE
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * NO DOCKER CHANGES
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
        echo "No dockerfiles changed – skip build & push."
      }
    }
  }

  post {
    success {
      echo "✅ ALL IMAGES BUILT & PUSHED SUCCESSFULLY"
    }
    failure {
      echo "❌ BUILD OR PUSH FAILED"
    }
    always {
      echo "Pipeline finished for commit ${env.GIT_COMMIT}"
    }
  }
}
