import aws_cdk as core
import aws_cdk.assertions as assertions

from lab.lab_stack import LabStack

# example tests. To run these tests, uncomment this file along with the example
# resource in lab/lab_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = LabStack(app, "lab")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
