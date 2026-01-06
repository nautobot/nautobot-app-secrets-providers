# AWS

## Authentication

No configuration is needed within Nautobot for this provider to operate. Instead, you must provide AWS credentials in one of the [methods supported by the `boto3` library](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#configuring-credentials).

Boto3 credentials can be configured in multiple ways (eight as of this writing) that are mirrored here:

1. Passing credentials as parameters in the `boto.client()` method
2. Passing credentials as parameters when creating a Session object
3. Environment variables
4. Shared credential file (`~/.aws/credentials`)
5. AWS config file (`~/.aws/config`)
6. Assume Role provider
7. Boto2 config file (`/etc/boto.cfg` and `~/.boto`)
8. Instance metadata service on an Amazon EC2 instance that has an IAM role configured.

**The AWS providers only support methods 3-8. Methods 1 and 2 ARE NOT SUPPORTED at this time.**

We highly recommend you defer to using environment variables for your deployment as specified in the credentials documentation linked above. The values specified in the linked documentation should be [set within your `~.bashrc`](https://nautobot.readthedocs.io/en/latest/installation/nautobot/#update-the-nautobot-bashrc) (or similar profile) on your system.

## Configuration

This is an example based on our recommended deployment pattern in the section above (method 3) that uses [environment variables](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#environment-variables). You will need to set these in the environment prior to starting Nautobot:

```shell
export AWS_ACCESS_KEY_ID=foo      # The access key for your AWS account.
export AWS_SECRET_ACCESS_KEY=bar  # The secret key for your AWS account.
```

Please refer to the [Nautobot documentation on updating your `.bashrc`](https://nautobot.readthedocs.io/en/latest/installation/nautobot/#update-the-nautobot-bashrc) for how to do this for production Nautobot deployments.
