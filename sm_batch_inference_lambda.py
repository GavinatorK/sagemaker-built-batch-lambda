import json
import boto3
import urllib
import csv
from time import gmtime, strftime, sleep

timestamp_suffix = strftime("%d-%H-%M-%S", gmtime())

sm_client = boto3.client("sagemaker")
s3 = boto3.client('s3')


def lambda_handler(event, context):
    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    try:
        callSMBatchInf(key, bucket, outBucket="veritoll-sm-inf", prefix="inf-xgb-")

    except Exception as e:
        print(e)

    return {
        'statusCode': 200,
        'body': json.dumps('completed inference call')
    }


def download_s3_obj(bucket, key):
    s3.download_file(bucket, key, '/tmp/' + key.split("/")[-1])
    return '/tmp/' + key.split("/")[-1]


def upload_s3_obj(bucket, key, local_path):
    s3.upload_file(local_path, bucket, key)


def removeHeader(bucket, key, outBucket):
    '''
    Check the input csv for inference and remove the header if present so the model doesn't error out
    bucket: input bucket
    objKey: file path
    '''
    local_path = download_s3_obj(bucket, key)
    out_path = local_path.split(".")[0] + "-2.csv"
    with open(local_path, "r") as f:

        has_header = csv.Sniffer().has_header(f.readline())
        f.seek(0)
        reader = csv.reader(f)
        if has_header:
            next(reader)

            with open(out_path, "w") as f2:
                csvwriter = csv.writer(f2)
                for row in reader:
                    csvwriter.writerow(row)

            upload_s3_obj(outBucket, "input/" + key, out_path)
            return
        else:
            upload_s3_obj(outBucket, "input/" + key, local_path)
            return


def callSMBatchInf(key, bucket, outBucket="veritoll-sm-inf", prefix="inf-xgb", model_name):
    # List Models that has name canvas in it
   
    ## we will grab the latest trained model. if you have multiple models, this can move out to config.json file to be saved in S3
    modelName = model_name
    print(modelName)
    # check if header is present and remove it
    removeHeader(bucket, key, outBucket)

    ## Create Input data reference for inference
    inf_data_s3_path = "s3://" + outBucket + "/input/" + key

    transform_job_name = "veritoll-rcf-" + timestamp_suffix

    transform_input = {
        "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": inf_data_s3_path}},
        "ContentType": "text/csv",
        "CompressionType": "None",
        "SplitType": "Line",
    }

    transform_output = {
        "S3OutputPath": "s3://{}/{}/inference-results".format(outBucket, prefix),
    }

    transform_resources = {"InstanceType": "ml.m5.4xlarge", "InstanceCount": 1}

    sm_client.create_transform_job(
        TransformJobName=transform_job_name,
        ModelName=modelName,
        TransformInput=transform_input,
        TransformOutput=transform_output,
        TransformResources=transform_resources,
    )
