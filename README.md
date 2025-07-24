# GitHub Repository Analytics

This project is a data pipeline that collects, processes, and analyzes data from GitHub repositories. It is composed of several serverless functions that work together to collect data such as Pull Requests, Issues, and Reviews, and store it in BigQuery for analysis.

## Project Structure

The project is divided into the following main components:

- **`function_1_dispatcher`**: This function is the starting point of the data collection pipeline. It is triggered by a Pub/Sub message and creates tasks in Cloud Tasks for each repository to be analyzed.
- **`function_2_worker`**: This function is triggered by a Cloud Task from the dispatcher. It fetches a list of all Pull Requests for a given repository and creates a separate task for each Pull request to be analyzed in detail.
- **`function_3_transformer`**: This function is triggered by a file creation event in a GCS bucket. It loads the collected data from GCS into a staging table in BigQuery.
- **`function_4_webhook_handler`**: This function is a webhook that listens for events from GitHub. It processes events such as new Pull Requests, Issues, and Reviews, and uploads the data to a GCS bucket.
- **`function_5_detail_collector`**: This function is triggered by a Cloud Task from the worker. It collects detailed information for a single Pull Request, including its reviews, and uploads the data to a GCS bucket.
- **`libs`**: This directory contains shared libraries used by the other functions, such as data models and a GitHub API client.

## Data Flow

1.  The `function_1_dispatcher` is triggered, which fetches a list of repositories to analyze.
2.  For each repository, the dispatcher creates a task for the `function_2_worker`.
3.  The `function_2_worker` fetches all Pull Requests for the repository and creates a task for each PR in the `function_5_detail_collector`.
4.  The `function_5_detail_collector` fetches detailed information for the PR, including reviews, and uploads the data to a GCS bucket.
5.  The `function_4_webhook_handler` listens for real-time events from GitHub and uploads the data to a GCS bucket.
6.  The `function_3_transformer` is triggered when a new file is uploaded to the GCS bucket, and it loads the data into a BigQuery staging table.

This modular architecture allows for a scalable and resilient data pipeline that can handle a large number of repositories and events.
