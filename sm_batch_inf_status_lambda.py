import json
import boto3
from botocore.exceptions import ClientError
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns_client = boto3.client('sns')

snsTopicName = 'mytesttopic'
sns_email_list = ['rkadiy@amazon.com']


# snsARN = 'ENTER YOUR TOPIC ARN HERE'
def sendSNSMessage(message):
    # Create an SNS Topic
    snsARN = createSNSTopic(snsTopicName)

    # Create list of existing subscriptions to the topic
    existing_subs = list_subscriptions(snsARN)

    # Subscribe new emails to SNS topic
    for email_addr in sns_email_list:
        if email_addr not in existing_subs:
            email_sub = subscribeSNS(snsARN, 'email', email_addr)
        else:
            existing_subs.remove(email_addr)

    # Remove any email addresses not in the email list
    result = unsubscribeSNS(snsARN, existing_subs)

    # Publish a message to the topic
    response = sns_client.publish(
        TargetArn=snsARN['TopicArn'],
        Message=message,
    )


def createSNSTopic(name):
    """
    Creates a notification topic if one does not already exist
    """

    # Check if topic already exists and return it if it does
    try:
        topic_list = sns_client.list_topics()
        for topic in topic_list['Topics']:
            if snsTopicName in topic['TopicArn']:
                logger.info("Topic %s already exists with ARN %s.", name, topic['TopicArn'])
                return topic
    except ClientError:
        logger.exception("Couldn't list SNS topics.")
        raise

    # Topic does not exist so create and return it
    try:
        topic = sns_client.create_topic(Name=name)
        logger.info(topic)
        logger.info("Created topic %s with ARN %s.", name, topic['TopicArn'])
    except ClientError:
        logger.exception("Couldn't create topic %s.", name)
        raise
    else:
        return topic


def subscribeSNS(topic, protocol, endpoint):
    """
    Subscribes an endpoint to the topic
    """
    try:
        subscription = sns_client.subscribe(
            TopicArn=topic['TopicArn'],
            Protocol=protocol,
            Endpoint=endpoint,
            ReturnSubscriptionArn=False
        )
        logger.info("Subscribed %s %s to topic %s.", protocol, endpoint, topic['TopicArn'])
    except ClientError:
        logger.exception(
            "Couldn't subscribe %s %s to topic %s.", protocol, endpoint, topic['TopicArn'])
        raise
    else:
        return subscription


def list_subscriptions(topic):
    """
    Create list of existing subscriptions to the topic
    """
    existing_subs = []
    for subs in sns_client.list_subscriptions_by_topic(TopicArn=topic['TopicArn'])['Subscriptions']:
        existing_subs.append(subs['Endpoint'])
    return existing_subs


def unsubscribeSNS(topic, unsub_email_list):
    """
    Unsubscribe a list of emails from SNS Topic
    """
    all_subscriptions = sns_client.list_subscriptions_by_topic(TopicArn=topic['TopicArn'])['Subscriptions']
    for subs in all_subscriptions:
        if subs['Endpoint'] in unsub_email_list:
            sns_client.unsubscribe(SubscriptionArn=subs['SubscriptionArn'])


def download_s3_obj(bucket, key):
    s3.download_file(bucket, key, '/tmp/' + key.split("/")[-1])
    return '/tmp/' + key.split("/")[-1]


def upload_s3_obj(bucket, key, local_path):
    s3.upload_file(local_path, bucket, key)


def addHeader(landingBucket, inputfileName, infBucket, infFileName):
    local_path_landing = download_s3_obj(landingBucket, inputfileName)

    local_path_inf = download_s3_obj(infBucket, infFileName)

    with open(local_path_landing, 'r') as f, open(local_path_inf, 'r') as inf, open("/tmp/prediction.csv",'w') as out:
        header = f.readline()

        header = "Predictions," + header

        out.write(header)

        xlines = inf.readlines()
        ylines = f.readlines()
        for line1, line2 in zip(xlines, ylines):
            out.write("{} {}\n".format(line1.rstrip(), line2.rstrip()))

    upload_s3_obj(infBucket, "header-output/some-out-file.csv", "/tmp/prediction.csv")

    return None


def lambda_handler(event, context):
    # grab transform job status"
    transform_job_name = event.get("detail").get("TransformJobName")
    transform_job_status = event.get("detail").get("TransformJobStatus")
    transform_input = event.get("detail").get("TransformInput").get("DataSource").get("S3DataSource").get("S3Uri")
    transform_output = event.get("detail").get("TransformOutput").get("S3OutputPath")
    transform_job_comp_time = event.get("detail").get("TransformEndTime")
    try:
        transform_failure_reason = event.get("detail").get("FailureReason")
    except:
        print("job is in progress or success")

    print("transform_input")
    print(transform_input)
    print("rest")
    print(event.get("detail").get("TransformInput"))
    print(transform_job_name)
    print(transform_output)

    # Update the prediction file with headers"

    # Reference to original file
    landingBucket = 'veritoll-landing'
    inputfileName = transform_input.split("/")[-1]

    # reference to inference results file
    infFileName = "/".join(x for x in transform_output.split("/")[3:]) + "/" + transform_input.split("/")[-1] + ".out"

    infBucket = transform_input.split("/")[2]

    print(infBucket)
    print(infFileName)

    # add header and upload to results folder
    addHeader(landingBucket, inputfileName, infBucket, infFileName)

    # Send notification of success

    sendSNSMessage("Prediction Updated for Next 180days starting {}".format(datetime.now().strftime("%Y-%b-%d")))

    return 200
