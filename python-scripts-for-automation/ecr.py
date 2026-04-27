import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

def list_ecr_images(region='eu-west-2'):
    try:
        # Create an ECR client
        ecr_client = boto3.client('ecr', region_name=region)

        # Get the list of all repositories
        repositories = ecr_client.describe_repositories()['repositories']

        if not repositories:
            print("No repositories found in your account.")
            return

        # Loop through each repository
        for repo in repositories:
            repo_name = repo['repositoryName']
            print(f"\nRepository: {repo_name}")

            # List all images in the current repository
            images = []
            paginator = ecr_client.get_paginator('list_images')
            response_iterator = paginator.paginate(repositoryName=repo_name)

            # Collect images from each page
            for page in response_iterator:
                for image_id in page['imageIds']:
                    images.append(image_id)

            # Display image tags and digests in a format suitable for Kubernetes manifests
            if not images:
                print(f"  No images found in repository '{repo_name}'.")
            else:
                print(f"  Images in repository '{repo_name}':")
                for image in images:
                    image_tag = image.get('imageTag', 'No Tag')
                    image_digest = image.get('imageDigest')
                    print(f"   - {repo_name}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{image_tag}")

    except NoCredentialsError:
        print("Error: AWS credentials not found. Please configure AWS credentials.")
    except PartialCredentialsError:
        print("Error: Incomplete AWS credentials. Please check your credentials.")
    except ClientError as e:
        print(f"An error occurred: {e}")
        # Handle specific client errors (e.g., throttling) here if needed
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    list_ecr_images(region='eu-west-2')