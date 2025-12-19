pipeline {
  agent any

  environment {
    GCR_REGION = "asia-southeast1"
    GCR_HOST   = "asia-southeast1-docker.pkg.dev"
  }

  stages {

    stage('Clean Workspace') {
      steps {
        cleanWs()
      }
    }

    stage('Git Checkout') {
      steps {
        git branch: 'airflow',
            url: 'https://github.com/abcdefya/Sentiment-Classifier-ML-System-on-K8S.git',
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
      stages {

        stage('Build Batch Docker Image') {
          steps {
            sh 'docker build -f dockerfiles/batch-processing/Dockerfile -t batch-app:latest .'
          }
        }

        stage('Auth GCP & Docker (Batch)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                /usr/bin/gcloud auth activate-service-account --key-file="$GCP_KEY"
                /usr/bin/gcloud config set project "$GCP_PROJECT"

                ACCESS_TOKEN=$(/usr/bin/gcloud auth print-access-token)
                echo "$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin ${GCR_HOST}
              '''
            }
          }
        }

        stage('Tag & Push Batch Image') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                GCR_REPO="${GCR_HOST}/${GCP_PROJECT}/docker-images"

                docker tag batch-app:latest ${GCR_REPO}/batch-app:latest
                docker push ${GCR_REPO}/batch-app:latest
              '''
            }
          }
        }
      }
    }

    /* =====================================================
     * Streaming Processing
     * ===================================================== */
    stage('Streaming: Build & Deploy') {
      when {
        changeset "dockerfiles/streaming-processing/**"
      }
      stages {

        stage('Build Streaming Docker Image') {
          steps {
            sh 'docker build -f dockerfiles/streaming-processing/Dockerfile -t stream-app:latest .'
          }
        }

        stage('Auth GCP & Docker (Streaming)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                /usr/bin/gcloud auth activate-service-account --key-file="$GCP_KEY"
                /usr/bin/gcloud config set project "$GCP_PROJECT"

                ACCESS_TOKEN=$(/usr/bin/gcloud auth print-access-token)
                echo "$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin ${GCR_HOST}
              '''
            }
          }
        }

        stage('Tag & Push Streaming Image (git commit)') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                SHORT_COMMIT=$(echo "$GIT_COMMIT" | cut -c1-7)
                IMAGE_TAG="git-${SHORT_COMMIT}"

                GCR_REPO="${GCR_HOST}/${GCP_PROJECT}/docker-images"

                echo "🔖 Streaming image tag: ${IMAGE_TAG}"

                docker tag stream-app:latest ${GCR_REPO}/stream-app:${IMAGE_TAG}
                docker push ${GCR_REPO}/stream-app:${IMAGE_TAG}
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
      stages {

        stage('Build Ingestion Docker Image') {
          steps {
            sh 'docker build -f dockerfiles/ingestion/Dockerfile -t ingestion-app:latest .'
          }
        }

        stage('Auth GCP & Docker (Ingestion)') {
          steps {
            withCredentials([
              file(credentialsId: 'gcp-artifact-key', variable: 'GCP_KEY'),
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                /usr/bin/gcloud auth activate-service-account --key-file="$GCP_KEY"
                /usr/bin/gcloud config set project "$GCP_PROJECT"

                ACCESS_TOKEN=$(/usr/bin/gcloud auth print-access-token)
                echo "$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin ${GCR_HOST}
              '''
            }
          }
        }

        stage('Tag & Push Ingestion Image') {
          steps {
            withCredentials([
              string(credentialsId: 'gcp-project-id', variable: 'GCP_PROJECT')
            ]) {
              sh '''
                GCR_REPO="${GCR_HOST}/${GCP_PROJECT}/docker-images"

                docker tag ingestion-app:latest ${GCR_REPO}/ingestion-app:latest
                docker push ${GCR_REPO}/ingestion-app:latest
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
        echo 'No changes in dockerfiles — skip Docker build/push.'
      }
    }
  }

  post {
    always {
      echo "Pipeline finished for commit ${env.GIT_COMMIT}"
    }
    success {
      echo "Build & push to Artifact Registry succeeded."
    }
    failure {
      echo "Build or push failed!"
    }
  }
}
