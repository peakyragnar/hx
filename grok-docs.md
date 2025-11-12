Consumption and Rate Limits
The cost of using our API is based on token consumptions. We charge different prices based on token category: - Prompt text, audio and image tokens - Charged at prompt token price - Cached prompt tokens - Charged at cached prompt token price - Completion tokens - Charged at completion token price - Reasoning tokens - Charged at completion token price

Visit Models and Pricing for general pricing, or xAI Console for pricing applicable to your team.

Each 
grok
 model has different rate limits. To check your team's rate limits, you can visit xAI Console Models Page.

Basic unit to calculate consumption — Tokens
Token is the base unit of prompt size for model inference and pricing purposes. It is consisted of one or more character(s)/symbol(s).

When a Grok model handles your request, an input prompt will be decomposed into a list of tokens through a tokenizer. The model will then make inference based on the prompt tokens, and generate completion tokens. After the inference is completed, the completion tokens will be aggregated into a completion response sent back to you.

Our system will add additional formatting tokens to the input/output token, and if you selected a reasoning model, additional reasoning tokens will be added into the total token consumption as well. Your actual consumption would be reflected either in the 
usage
 object returned in the API response, or in Usage Explorer on the xAI Console.

You can use Tokenizer on xAI Console to visualize tokens a given text prompt, or use Tokenize text endpoint on the API.

Tokenizer in xAI Console
Text tokens
Tokens can be either of a whole word, or smaller chunks of character combinations. The more common a word is, the more likely it would be a whole token.

For example, Flint is broken down into two tokens, while Michigan is a whole token.

Tokenized result for 'Flint, Michigan'
In another example, most words are tokens by themselves, but "drafter" is broken down into "dra" and "fter", and "postmaster" is broken down into "post" and "master".

Tokenized paragraph
For a given text/image/etc. prompt or completion sequence, different tokenizers may break it down into different lengths of lists.

Different Grok models may also share or use different tokenizers. Therefore, the same prompt/completion sequence may not have the same amount of tokens across different models.

The token count in a prompt/completion sequence should be approximately linear to the sequence length.

Image prompt tokens
Each image prompt will take between 256 to 1792 tokens, depending on the size of the image. The image + text token count must be less than the overall context window of the model.

Estimating consumption with tokenizer on xAI Console or through API
The tokenizer page or API might display less token count than the actual token consumption. The inference endpoints would automatically add pre-defined tokens to help our system process the request.

On xAI Console, you can use the tokenizer page to estimate how many tokens your text prompt will consume. For example, the following message would consume 5 tokens (the actual consumption may vary because of additional special tokens added by the system).

Message body:

JSON


[
  {
    "role": "user",
    "content": "How is the weather today?"
  }
]
Tokenize result on Tokenizer page:

'How is the weather today?' in Tokenizer on xAI Console
You can also utilize the Tokenize Text API endpoint to tokenize the text, and count the output token array length.

Cached prompt tokens
When you send the same prompt multiple times, we may cache your prompt tokens. This would result in reduced cost for these tokens at the cached token rate, and a quicker response.

Reasoning tokens
The model may use reasoning to process your request. The reasoning content is returned in the response's 
reasoning_content
 field. The reasoning token consumption will be counted separately from 
completion_tokens
, but will be counted in the 
total_tokens
.

The reasoning tokens will be charged at the same price as 
completion_tokens
.

grok-4
 does not return 
reasoning_content

Hitting rate limits
To request a higher rate limit, please email support@x.ai with your anticipated volume.

For each tier, there is a maximum amount of requests per minute and tokens per minute. This is to ensure fair usage by all users of the system.

Once your request frequency has reached the rate limit, you will receive error code 
429
 in response.

You can either:

Upgrade your team to higher tiers
Change your consumption pattern to send fewer requests
Checking token consumption
In each completion response, there is a 
usage
 object detailing your prompt and completion token count. You might find it helpful to keep track of it, in order to avoid hitting rate limits or having cost surprises.

JSON


"usage": {
    "prompt_tokens":37,
    "completion_tokens":530,
    "total_tokens":800,
    "prompt_tokens_details": {
        "text_tokens":37,
        "audio_tokens":0,
        "image_tokens":0,
        "cached_tokens":8
    },
    "completion_tokens_details": {
        "reasoning_tokens":233,
        "audio_tokens":0,
        "accepted_prediction_tokens":0,
        "rejected_prediction_tokens":0
    },
    "num_sources_used":0
}
You can also check with the xAI, OpenAI or Anthropic SDKs.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import system, user
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
model="grok-4",
messages=[system("You are Grok, a chatbot inspired by the Hitchhikers Guide to the Galaxy.")]
)
chat.append(user("What is the meaning of life, the universe, and everything?"))
response = chat.sample()
print(response.usage)

Regional Endpoints
By default, you can access our API at 
https://api.x.ai
. This is the most suitable endpoint for most customers, as the request will be automatically routed by us to be processed in the region with lowest latency for your request.

For example, if you are based in US East Coast and send your request to 
https://api.x.ai
, your request will be forwarded to our 
us-east-1
 region and we will try to process it there first. If there is not enough computing resource in 
us-east-1
, we will send your request to other regions that are geographically closest to you and can handle the request.

Using a regional endpoint
If you have specific data privacy requirements that would require the request to be processed within a specified region, you can leverage our regional endpoint.

You can send your request to 
https://<region-name>.api.x.ai
. For the same example, to send request from US East Coast to 
us-east-1
, you will now send the request to 
https://us-east-1.api.x.ai
. If for some reason, we cannot handle your request in 
us-east-1
, the request will fail.

Example of using regional endpoints
If you want to use a regional endpoint, you need to specify the endpoint url when making request with SDK. In xAI SDK, this is specified through the 
api_host
 parameter.

For example, to send request to 
us-east-1
:

Python

import os
from xai_sdk import Client
from xai_sdk.chat import user
client = Client(
api_key=os.getenv("XAI_API_KEY"),
api_host="us-east-1.api.x.ai" # Without the https://
)
chat = client.chat.create(model="grok-4")
chat.append(user("What is the meaning of life?"))
completion = chat.sample()
Model availability across regions
While we strive to make every model available across all regions, there could be occasions where some models are not available in some regions.

By using the global 
https://api.x.ai
 endpoint, you would have access to all models available to your team, since we route your request automatically. If you're using a regional endpoint, please refer to xAI Console for the available models to your team in each region, or Models and Pricing for the publicly available models.

 Collections
Collections offers xAI API users a robust set of tools and methods to seamlessly integrate their enterprise requirements and internal knowledge bases with the xAI API. This feature enables efficient management, retrieval, and utilization of documents to enhance AI-driven workflows and applications.

There are two entities that user can create within Collections service:

file
A 
file
 is a single entity of a user-uploaded file.
collection
A 
collection
 is a group of 
files
 linked together, with an embedding index for efficient retrieval of each 
file
.
When you create a 
collection
 you have the option to automatically generate embeddings for any files uploaded to that 
collection
. You can then perform semantic search across files in multiple 
collections
.
A single 
file
 can belong to multiple 
collections
 but must be part of at least one 
collection
.
File storage and retrieval
Visit the Collections tab on the xAI Console to create a new 
collection
. Once created, you can add 
files
 to the 
collection
.

All your 
collections
 and their associated 
files
 can be viewed in the Collections tab.

Your 
files
 and their embedding index are securely encrypted and stored on our servers. The index enables efficient retrieval of 
files
 during a relevance search.

Usage limits
User can upload a maximum of 100,000 files per collection. We do not place any limits on the file size, etc.

Data Privacy
We do not use user data stored on Collections for model training purposes by default, unless user has given consent.

Using Management API
Some enterprise users may prefer to manage their account details programmatically rather than manually through the xAI Console. For this reason, we have developed a Management API to enable enterprise users to efficiently manage their team details.

You can read the endpoint specifications and descriptions at Management API Reference.

You need to get a management key, which is separate from your API key, to use the management API. The management key can be obtained at xAI Console -> Settings -> Management Keys.

Management API keys table in xAI Console settings showing available management keys
The base URL is at 
https://management-api.x.ai
, which is also different from the inference API.

Operations related to API Keys
You can create, list, update and delete API keys via the management API.

You can also manage the access control lists (ACLs) associated with the API keys.

The available ACL types are:

api-key:model
api-key:endpoint
To enable all models and endpoints available to your team, use:

api-key:model:*
api-key:endpoint:*
Or if you need to specify the particular endpoint available to the API:

api-key:endpoint:chat
 for chat and vision models
api-key:endpoint:image
 for image generation models
And to specify models the API key has access to:

api-key:model:<model name such as grok-4>
Create an API key
An example to create an API key with all models and endpoints enabled, limiting requests to 5 queries per second and 100 queries per minute, without token number restrictions.

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/api-keys \
    -X POST \
    -H "Authorization: Bearer <Your Management API Key>" \
    -d '{
            "name": "My API key",
            "acls": ["api-key:model:*", "api-key:endpoint:*"],
            "qps": 5,
            "qpm": 100,
            "tpm": null
        }'
Specify 
tpm
 to any integer string to limit the number of tokens produced/consumed per minute. When the token rate limit is triggered, new requests will be rejected and in-flight requests will continue processing.

The newly-created API key will be returned in the 
"apiKey"
 field of the response object. The API Key ID is returned as 
"apiKeyId"
 in the response body as well, which is useful for updating and deleting operations.

List API keys
To retrieve a list of API keys from a team, you can run the following:

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/api-keys?pageSize=10&paginationToken= \
    -H "Authorization: Bearer <Your Management API Key>"
You can customize the query parameters such as 
pageSize
 and 
paginationToken
.

Update an API key
You can update an API key after it has been created. For example, to update the 
qpm
 of an API key:

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/api-keys \
    -X PUT \
    -d '{
            "apiKey": "<The apiKey Object with updated qpm>",
            "fieldMask": "qpm",
        }'
Or to update the 
name
 of an API key:

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/api-keys \
    -X PUT \
    -d '{
            "apiKey": "<The apiKey Object with updated name>",
            "fieldMask": "name",
        }'
Delete an API key
You can also delete an API key with the following:

Bash


curl https://management-api.x.ai/auth/api-keys/{apiKeyId} \
    -X DELETE \
    -H "Authorization: Bearer <Your Management API Key>"
Check propagation status of API key across clusters
There could be a slight delay between creating an API key, and the API key being available for use across all clusters.

You can check the propagation status of the API key via API.

Bash


curl https://management-api.x.ai/auth/api-keys/{apiKeyId}/propagation \
    -H "Authorization: Bearer <Your Management API Key>"
List all models available for the team
You can list all the available models for a team with our management API as well.

The model names in the output can be used with setting ACL string on an API key as 
api-key:model:<model-name>

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/models \
    -H "Authorization: Bearer <Your Management API Key>"
Access Control List (ACL) management
We also offer endpoint to list possible ACLs for a team. You can then apply the endpoint ACL strings to your API keys.

To view possible endpoint ACLs for a team's API keys:

Bash


curl https://management-api.x.ai/auth/teams/{teamId}/endpoints \
    -H "Authorization: Bearer <Your Management API Key>"

Usage Explorer
Sometimes as a team admin, you might want to monitor the API consumption, either to track spending, or to detect anomalies. xAI Console provides an easy-to-use Usage Explorer for team admins to track API usage across API keys, models, etc.

Basic usage
Usage Explorer page provides intuitive dropdown menus for you to customize how you want to view the consumptions.

For example, you can view your daily credit consumption with 
Granularity: Daily
:

Daily credit consumption in xAI Console Usage Explorer
By default, the usage is calculated by cost in US Dollar. You can select Dimension -> Tokens or Dimension -> Billing items to change the dimension to token count or billing item count.

Usage by token in xAI Console Usage Explorer
You can also see the usage with grouping. This way, you can easily compare the consumption across groups. In this case, we are trying to compare consumptions across test and production API keys, so we select 
Group by: API Key
:

Usage by API Key in xAI Console Usage Explorer
Filters
The basic usage should suffice if you are only viewing general information. However, you can also use filters to conditionally display information.

The filters dropdown gives you the options to filter by a particular API key, a model, a request IP, a cluster, or the token type.

Debugging Errors
When you send a request, you would normally get a 
200 OK
 response from the server with the expected response body. If there has been an error with your request, or error with our service, the API endpoint will typically return an error code with error message.

If there is an ongoing service disruption, you can visit https://status.x.ai for the latest updates. The status is also available via RSS at https://status.x.ai/feed.xml.


The service status is also indicated in the navigation bar of this site.

Most of the errors will be accompanied by an error message that is self-explanatory. For typical status codes of each endpoint, visit API Reference or view our OpenAPI Document.

Status Codes
Here is a list of potential errors and statuses arranged by status codes.

4XX Status Codes
Status Code	Endpoints	Cause	Solution
400
Bad Request	All Endpoints	- A 
POST
 method request body specified an invalid argument, or a 
GET
 method with dynamic route has an invalid param in the URL.
- An incorrect API key is supplied.	- Please check your request body or request URL.
401
Unauthorized	All Endpoints	- No authorization header or an invalid authorization token is provided.	- Supply an 
Authorization: Bearer Token <XAI_API_KEY>
 in the request header. You can get a new API key on xAI Console.
403
Forbidden	All Endpoints	- Your API key/team doesn't have permission to perform the action.
- Your API key/team is blocked.	- Ask your team admin for permission.
404
Not Found	All Endpoints	- A model specified in a 
POST
 method request body is not found.
- Trying to reach an invalid endpoint URL. (Misspelled URL)	- Check your request body and endpoint URL with our API Reference.
405
Method Not Allowed	All Endpoints	- The request method is not allowed. For example, sending a 
POST
 request to an endpoint supporting only 
GET
.	- Check your request method with our API Reference.
415
Unsupported Media Type	All Endpoints Supporting 
POST
 Method	- An empty request body in 
POST
 requests.
- Not specifying 
Content-Type: application/json
 header.	- Add a valid request body.
- Ensure 
Content-Type: application/json
 header is present in the request header.
422
Unprocessable Entity	All Endpoints Supporting 
POST
 Method	- An invalid format for a field in the 
POST
 request body.	- Check your request body is valid. You can find more information from API Reference.
429
Too Many Requests	All Inference Endpoints	- You are sending requests too frequently and reaching rate limit	- Reduce your request rate or increase your rate limit. You can find your current rate limit on xAI Console.
2XX Error Codes
Status Code	Endpoints	Cause	Solution
202
Accepted	
/v1/chat/deferred-completion/{request_id}
- Your deferred chat completion request is queued for processing, but the response is not available yet.	- Wait for request processing.
Bug Report
If you believe you have encountered a bug and would like to contribute to our development process, email API Bug Report to support@x.ai with your API request and response and relevant logs.

You can also chat in the 
#help
 channel of our xAI API Developer Discord.

 Stateful Response with Responses API
Vercel AI SDK Support: The Responses API is not yet supported in the Vercel AI SDK. Please use the xAI SDK or OpenAI SDK for this functionality.

Responses API is a new way of interacting with our models via API. It allows a stateful interaction with our models, where previous input prompts, reasoning content and model responses are saved by us. A user can continue the interaction by appending new prompt messages, rather than sending all of the previous messages.

Although you don't need to enter the conversation history in the request body, you will still be billed for the entire conversation history when using Responses API. The cost might be reduced as the conversation history might be automatically cached.

The responses will be stored for 30 days, after which they will be removed. If you want to continue a response after 30 days, please store your responses history as well as the encrypted thinking content to create a new response. The encrypted thinking content can then be sent in the request body to give you a better result. See Returning encrypted thinking content for more information on retrieving encrypted content.

Prerequisites
xAI Account: You need an xAI account to access the API.
API Key: Ensure that your API key has access to the chat endpoint and the chat model is enabled.
If you don't have these and are unsure of how to create one, follow the Hitchhiker's Guide to Grok.

You can create an API key on the xAI Console API Keys Page.

Set your API key in your environment:

Bash


export XAI_API_KEY="your_api_key"
Creating a new model response
The first step in using Responses API is analogous to using Chat Completions API. You will create a new response with prompts.

instructions
 parameter is currently not supported. The API will return an error if it is specified.

When sending images, it is advised to set 
store
 parameters to 
false
. Otherwise the request may fail.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
chat = client.chat.create(model="grok-4", store_messages=True)
chat.append(system("You are Grok, a chatbot inspired by the Hitchhiker's Guide to the Galaxy."))
chat.append(user("What is the meaning of life, the universe, and everything?"))
response = chat.sample()
print(response)
# The response id that can be used to continue the conversation later
print(response.id)
If no system prompt is desired, for non-xAI SDK users, the request's input parameter can be simplified as a string user prompt:


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
chat = client.chat.create(model="grok-4", store_messages=True)
chat.append(user("What is 101*3"))
response = chat.sample()
print(response)
# The response id that can be used to continue the conversation later
print(response.id)
Returning encrypted thinking content
If you want to return the encrypted thinking traces, you need to specify 
use_encrypted_content=True
 in xAI SDK or gRPC request message, or 
include: ["reasoning.encrypted_content"]
 in the request body.

Modify the steps to create a chat client (xAI SDK) or change the request body as following:


Python
Other

chat = client.chat.create(model="grok-4",
        store_messages=True,
        use_encrypted_content=True)
See Adding encrypted thinking content on how to use the returned encrypted thinking content.

Chaining the conversation
We now have the 
id
 of the first response. With Chat Completions API, we typically send a stateless new request with all the previous messages.

With Responses API, we can send the 
id
 of the previous response, and the new messages to append to it.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
chat = client.chat.create(model="grok-4", store_messages=True)
chat.append(system("You are Grok, a chatbot inspired by the Hitchhiker's Guide to the Galaxy."))
chat.append(user("What is the meaning of life, the universe, and everything?"))
response = chat.sample()
print(response)
# The response id that can be used to continue the conversation later
print(response.id)
# New steps
chat = client.chat.create(
    model="grok-4",
    previous_response_id=response.id,
    store_messages=True,
)
chat.append(user("What is the meaning of 42?"))
second_response = chat.sample()
print(second_response)
# The response id that can be used to continue the conversation later
print(second_response.id)
Adding encrypted thinking content
After returning the encrypted thinking content, you can also add it to a new response's input:


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
chat = client.chat.create(model="grok-4", store_messages=True, use_encrypted_content=True)
chat.append(system("You are Grok, a chatbot inspired by the Hitchhiker's Guide to the Galaxy."))
chat.append(user("What is the meaning of life, the universe, and everything?"))
response = chat.sample()
print(response)
# The response id that can be used to continue the conversation later
print(response.id)
# New steps
chat.append(response)  ## Append the response and the SDK will automatically add the outputs from response to message history
chat.append(user("What is the meaning of 42?"))
second_response = chat.sample()
print(second_response)
# The response id that can be used to continue the conversation later
print(second_response.id)
Retrieving a previous model response
If you have a previous response's ID, you can retrieve the content of the response.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
response = client.chat.get_stored_completion("<The previous response's id>")
print(response)
Delete a model response
If you no longer want to store the previous model response, you can delete it.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    management_api_key=os.getenv("XAI_MANAGEMENT_API_KEY"),
    timeout=3600,
)
response = client.chat.delete_stored_completion("<The previous response's id>")
print(response)

Chat
Text in, text out. Chat is the most popular feature on the xAI API, and can be used for anything from summarizing articles, generating creative writing, answering questions, providing customer support, to assisting with coding tasks.

Prerequisites
xAI Account: You need an xAI account to access the API.
API Key: Ensure that your API key has access to the chat endpoint and the chat model is enabled.
If you don't have these and are unsure of how to create one, follow the Hitchhiker's Guide to Grok.

You can create an API key on the xAI Console API Keys Page.

Set your API key in your environment:

Bash


export XAI_API_KEY="your_api_key"
A Basic Chat Completions Example
You can also stream the response, which is covered in Streaming Response.

The user sends a request to the xAI API endpoint. The API processes this and returns a complete response.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    timeout=3600, # Override default timeout with longer timeout for reasoning models
)
chat = client.chat.create(model="grok-4")
chat.append(system("You are a PhD-level mathematician."))
chat.append(user("What is 2 + 2?"))
response = chat.sample()
print(response.content)
Response:


Python

Javascript
Other

'2 + 2 equals 4.'
Conversations
The xAI API is stateless and does not process new request with the context of your previous request history.

However, you can provide previous chat generation prompts and results to a new chat generation request to let the model process your new request with the context in mind.

An example message:

JSON


{
  "role": "system",
  "content": [{ "type": "text", "text": "You are a helpful and funny assistant."}]
}
{
  "role": "user",
  "content": [{ "type": "text", "text": "Why don't eggs tell jokes?" }]
},
{
  "role": "assistant",
  "content": [{ "type": "text", "text": "They'd crack up!" }]
},
{
  "role": "user",
  "content": [{"type": "text", "text": "Can you explain the joke?"}],
}
By specifying roles, you can change how the the model ingests the content. The 
system
 role content should define, in an instructive tone, the way the model should respond to user request. The 
user
 role content is usually used for user requests or data sent to the model. The 
assistant
 role content is usually either in the model's response, or when sent within the prompt, indicates the model's response as part of conversation history.

Message role order flexibility
Unlike some models from other providers, one of the unique aspects of xAI API is its flexibility with message role ordering:

No Order Limitation: You can mix 
system
, 
user
, or 
assistant
 roles in any order for your conversation context.
Example 1 - Multiple System Messages:

JSON


[
  { "role": "system", "content": "..." },
  { "role": "system", "content": "..." },
  { "role": "user", "content": "..." },
  { "role": "user", "content": "..." }
]
Example 2 - User Messages First:

JSON


[
  { "role": "user", "content": "..." },
  { "role": "user", "content": "..." },
  { "role": "system", "content": "..." }
]
Reasoning
grok-4-fast-non-reasoning
 variant is based on 
grok-4-fast-reasoning
 with reasoning disabled.

presencePenalty
, 
frequencyPenalty
 and 
stop
 parameters are not supported by reasoning models. Adding them in the request would result in error.

Key Features
Think Before Responding: Thinks through problems step-by-step before delivering an answer.
Math & Quantitative Strength: Excels at numerical challenges and logic puzzles.
Reasoning Trace: The model's thoughts are available via the 
reasoning_content
 or 
encrypted_content
 field in the response completion object (see example below).
You can access the model's raw thinking trace via the 
message.reasoning_content
 of the chat completion response. Only 
grok-3-mini
 returns 
reasoning_content
.


grok-3
, 
grok-4
 and 
grok-4-fast-reasoning
 do not return 
reasoning_content
. It may optionally return encrypted reasoning content instead.

Encrypted Reasoning Content
For 
grok-4
, the reasoning content is encrypted by us and sent back if 
use_encrypted_content
 is set to 
true
. You can send the encrypted content back to provide more context to a previous conversation. See Stateful Response with Responses API for more details on how to use the content.

Control how hard the model thinks
reasoning_effort
 is not supported by 
grok-3
, 
grok-4
 and 
grok-4-fast-reasoning
. Specifying 
reasoning_effort
 parameter will get an error response. Only 
grok-3-mini
 supports 
reasoning_effort
.

The 
reasoning_effort
 parameter controls how much time the model spends thinking before responding. It must be set to one of these values:

low
: Minimal thinking time, using fewer tokens for quick responses.
high
: Maximum thinking time, leveraging more tokens for complex problems.
Choosing the right level depends on your task: use 
low
 for simple queries that should complete quickly, and 
high
 for harder problems where response latency is less important.

Usage Example
Here’s a simple example using 
grok-3-mini
 to multiply 101 by 3.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import system, user
client = Client(
    api_key=os.getenv("XAI_API_KEY"),
    timeout=3600, # Override default timeout with longer timeout for reasoning models
)
chat = client.chat.create(
    model="grok-3-mini",
    reasoning_effort="high",
    messages=[system("You are a highly intelligent AI assistant.")],
)
chat.append(user("What is 101*3?"))
response = chat.sample()
print("Final Response:")
print(response.content)
print("Number of completion tokens:")
print(response.usage.completion_tokens)
print("Number of reasoning tokens:")
print(response.usage.reasoning_tokens)
Sample Output
Output


Final Response:
The result of 101 multiplied by 3 is 303.
Number of completion tokens:
14
Number of reasoning tokens:
310
Notes on Consumption
When you use a reasoning model, the reasoning tokens are also added to your final consumption amount. The reasoning token consumption will likely increase when you use a higher 
reasoning_effort
 setting.

 Overview
The xAI API supports agentic server-side tool calling which enables the model to autonomously explore, search, and execute code to solve complex queries. Unlike traditional tool-calling where clients must handle each tool invocation themselves, xAI's agentic API manages the entire reasoning and tool-execution loop on the server side.

xAI Python SDK Users: Version 1.3.1 of the xai-sdk package is required to use the agentic tool calling API.

Tools Pricing
Agentic requests are priced based on two components: token usage and tool invocations. Since the agent autonomously decides how many tools to call, costs scale with query complexity.

For more details on Tools pricing, please check out the pricing page.

Agentic Tool Calling
When you provide server-side tools to a request, the xAI server orchestrates an autonomous reasoning loop rather than returning tool calls for you to execute. This creates a seamless experience where the model acts as an intelligent agent that researches, analyzes, and responds automatically.

Behind the scenes, the model follows an iterative reasoning process:

Analyzes the query and current context to determine what information is needed
Decides what to do next: Either make a tool call to gather more information or provide a final answer
If making a tool call: Selects the appropriate tool and parameters based on the reasoning
Executes the tool in real-time on the server and receives the results
Processes the tool response and integrates it with previous context and reasoning
Repeats the loop: Uses the new information to decide whether more research is needed or if a final answer can be provided
Returns the final response once the agent determines it has sufficient information to answer comprehensively
This autonomous orchestration enables complex multi-step research and analysis to happen automatically, with clients seeing the final result as well as optional real-time progress indicators like tool call notifications during streaming.

Core Capabilities
Web Search: Real-time search across the internet with the ability to both search the web and browse web pages.
X Search: Semantic and keyword search across X posts, users, and threads.
Code Execution: The model can write and execute Python code for calculations, data analysis, and complex computations.
Image/Video Understanding: Optional visual content understanding and analysis for search results encountered (video understanding is only available for X posts).
Collections Search: The model can search through your uploaded knowledge bases and collections to retrieve relevant information.
Remote MCP Tools: Connect to external MCP servers to access custom tools.
Document Search: Upload files and chat with them using intelligent document search. This tool is automatically enabled when you attach files to a chat message.
Quick Start
We strongly recommend using the xAI Python SDK in streaming mode when using agentic tool calling. Doing so grants you the full feature set of the API, including the ability to get real-time observability and immediate feedback during potentially long-running requests.

Here is a quick start example of using the agentic tool calling API.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search, x_search, code_execution
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    # All server-side tools active
    tools=[
        web_search(),
        x_search(),
        code_execution(),
    ],
)
# Feel free to change the query here to a question of your liking
chat.append(user("What are the latest updates from xAI?"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
You will be able to see output like:

Output


Thinking... (270 tokens)
Calling tool: x_user_search with arguments: {"query":"xAI official","count":1}
Thinking... (348 tokens)
Calling tool: x_user_search with arguments: {"query":"xAI","count":5}
Thinking... (410 tokens)
Calling tool: x_keyword_search with arguments: {"query":"from:xai","limit":10,"mode":"Latest"}
Thinking... (667 tokens)
Calling tool: web_search with arguments: {"query":"xAI latest updates site:x.ai","num_results":5}
Thinking... (850 tokens)
Calling tool: browse_page with arguments: {"url": "https://x.ai/news"}
Thinking... (1215 tokens)
Final Response:
### Latest Updates from xAI (as of October 12, 2025)
xAI primarily shares real-time updates via their official X (Twitter) account (@xai), with more formal announcements on their website (x.ai). Below is a summary of the most recent developments...
... full response omitted for brevity
Citations:
[
'https://x.com/i/user/1912644073896206336',
'https://x.com/i/user/1019237602585645057',
'https://x.com/i/status/1975607901571199086',
'https://x.com/i/status/1975608122845896765',
'https://x.com/i/status/1975608070245175592',
'https://x.com/i/user/1603826710016819209',
'https://x.com/i/status/1975608007250829383',
'https://status.x.ai/',
'https://x.com/i/user/150543432',
'https://x.com/i/status/1975608184711880816',
'https://x.com/i/status/1971245659660718431',
'https://x.com/i/status/1975608132530544900',
'https://x.com/i/user/1661523610111193088',
'https://x.com/i/status/1977121515587223679',
'https://x.ai/news/grok-4-fast',
'https://x.com/i/status/1975608017396867282',
'https://x.ai/',
'https://x.com/i/status/1975607953391755740',
'https://x.com/i/user/1875560944044273665',
'https://x.ai/news',
'https://docs.x.ai/docs/release-notes'
]
Usage:
completion_tokens: 1216
prompt_tokens: 29137
total_tokens: 31568
prompt_text_tokens: 29137
reasoning_tokens: 1215
cached_prompt_text_tokens: 22565
server_side_tools_used: SERVER_SIDE_TOOL_X_SEARCH
server_side_tools_used: SERVER_SIDE_TOOL_X_SEARCH
server_side_tools_used: SERVER_SIDE_TOOL_X_SEARCH
server_side_tools_used: SERVER_SIDE_TOOL_WEB_SEARCH
server_side_tools_used: SERVER_SIDE_TOOL_WEB_SEARCH
{'SERVER_SIDE_TOOL_X_SEARCH': 3, 'SERVER_SIDE_TOOL_WEB_SEARCH': 2}
Server Side Tool Calls:
[id: "call_51132959"
function {
  name: "x_user_search"
  arguments: "{"query":"xAI official","count":1}"
}
, id: "call_00956753"
function {
  name: "x_user_search"
  arguments: "{"query":"xAI","count":5}"
}
, id: "call_07881908"
function {
  name: "x_keyword_search"
  arguments: "{"query":"from:xai","limit":10,"mode":"Latest"}"
}
, id: "call_43296276"
function {
  name: "web_search"
  arguments: "{"query":"xAI latest updates site:x.ai","num_results":5}"
}
, id: "call_70310550"
function {
  name: "browse_page"
  arguments: "{"url": "https://x.ai/news"}"
}
]
Understanding the Agentic Tool Calling Response
The agentic tool calling API provides rich observability into the autonomous research process. This section dives deep into the original code snippet above, covering key ways to effectively use the API and understand both real-time streaming responses and final results:

Real-time server-side tool calls
When executing agentic requests using streaming, you can observe every tool call decision the model makes in real-time via the 
tool_calls
 attribute on the 
chunk
 object. This shows the exact parameters the agent chose for each tool invocation, giving you visibility into its search strategy. Occasionally the model may decide to invoke multiple tools in parallel during a single turn, in which case each entry in the list of 
tool_calls
 would represent one of those parallel tool calls; otherwise, only a single entry would be present in 
tool_calls
.

Note: Only the tool call invocations themselves are shown - server-side tool call outputs are not returned in the API response. The agent uses these outputs internally to formulate its final response, but they are not exposed to the user.

When using the xAI Python SDK in streaming mode, it will automatically accumulate the 
tool_calls
 into the 
response
 object for you, letting you access a final list of all the server-side tool calls made during the agentic loop. This is demonstrated in the section below.

Python


for tool_call in chunk.tool_calls:
    print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
Output


Calling tool: x_user_search with arguments: {"query":"xAI official","count":1}
Calling tool: x_user_search with arguments: {"query":"xAI","count":5}
Calling tool: x_keyword_search with arguments: {"query":"from:xai","limit":10,"mode":"Latest"}
Calling tool: web_search with arguments: {"query":"xAI latest updates site:x.ai","num_results":5}
Calling tool: browse_page with arguments: {"url": "https://x.ai/news"}
Citations
The 
citations
 attribute on the 
response
 object provides a comprehensive list of URLs for all sources the agent encountered during its search process. They are only returned when the agentic request completes and are not available in real-time during streaming. Citations are automatically collected from successful tool executions and provide full traceability of the agent's information sources.

Note that not every URL here will necessarily be relevant to the final answer, as the agent may examine a particular source and determine it is not sufficiently relevant to the user's original query.

Python


response.citations
Output


[
'https://x.com/i/user/1912644073896206336',
'https://x.com/i/status/1975607901571199086',
'https://x.ai/news',
'https://docs.x.ai/docs/release-notes',
...
]
Server-side Tool Calls vs Tool Usage
The API provides two related but distinct metrics for server-side tool executions:

tool_calls
 - All Attempted Calls

Python


response.tool_calls
Returns a list of all attempted tool calls made during the agentic process. Each entry is a ToolCall object containing:

id
: Unique identifier for the tool call
function.name
: The name of the specific server-side tool called
function.arguments
: The parameters passed to the server-side tool
This includes every tool call attempt, even if some fail.

Output


[id: "call_51132959"
function {
  name: "x_user_search"
  arguments: "{"query":"xAI official","count":1}"
}
, id: "call_07881908"
function {
  name: "x_keyword_search"
  arguments: "{"query":"from:xai","limit":10,"mode":"Latest"}"
}
, id: "call_43296276"
function {
  name: "web_search"
  arguments: "{"query":"xAI latest updates site:x.ai","num_results":5}"
}
]
server_side_tool_usage
 - Successful Calls (Billable)

Python


response.server_side_tool_usage
Returns a map of successfully executed tools and their invocation counts. This represents only the tool calls that returned meaningful responses and is what determines your billing.

Output


{'SERVER_SIDE_TOOL_X_SEARCH': 3, 'SERVER_SIDE_TOOL_WEB_SEARCH': 2}
Tool Call Function Names vs Usage Categories
The function names in 
tool_calls
 represent the precise/exact name of the tool invoked by the model, while the entries in 
server_side_tool_usage
 provide a more high-level categorization that aligns with the original tool passed in the 
tools
 array of the request.

Function Name to Usage Category Mapping:

Usage Category	Function Name(s)
SERVER_SIDE_TOOL_WEB_SEARCH
web_search
, 
web_search_with_snippets
, 
browse_page
SERVER_SIDE_TOOL_X_SEARCH
x_user_search
, 
x_keyword_search
, 
x_semantic_search
, 
x_thread_fetch
SERVER_SIDE_TOOL_CODE_EXECUTION
code_execution
SERVER_SIDE_TOOL_VIEW_X_VIDEO
view_x_video
SERVER_SIDE_TOOL_VIEW_IMAGE
view_image
SERVER_SIDE_TOOL_COLLECTIONS_SEARCH
collections_search
SERVER_SIDE_TOOL_MCP
{server_label}.{tool_name}
 if 
server_label
 provided, otherwise 
{tool_name}
When Tool Calls and Usage Differ
In most cases, 
tool_calls
 and 
server_side_tool_usage
 will show the same tools. However, they can differ when:

Failed tool executions: The model attempts to browse a non-existent webpage, fetch a deleted X post, or encounters other execution errors
Invalid parameters: Tool calls with malformed arguments that can't be processed
Network or service issues: Temporary failures in the tool execution pipeline
The agentic system is robust enough to handle these failures gracefully, updating its trajectory and continuing with alternative approaches when needed.

Billing Note: Only successful tool executions (
server_side_tool_usage
) are billed. Failed attempts are not charged.

Server-side Tool Call and Client-side Tool Call
Agentic tool calling supports mixing server-side tools and client-side tools, which enables more use cases when some private tools and data are needed during the agentic tool calling process.

To determine whether the received tool calls need to be executed by the client side, you can simply check the type of the tool call.

For xAI Python SDK users, you can use the provided 
get_tool_call_type
 function to get the type of the tool calls.

For a full guide into requests that mix server-side and client-side tools, please check out the advanced usage page.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is the minimum requirement to use the 
get_tool_call_type
 function.

Python


# ...
response = chat.sample()
from xai_sdk.tools import get_tool_call_type
for tool_call in response.tool_calls:
    print(get_tool_call_type(tool_call))
The available tool call types are listed below:

Tool call types	Description
"client_side_tool"
Indicates this tool call is a client-side tool call, and an invocation to this function on the client side is required and the tool output needs to be appended to the chat
"web_search_tool"
Indicates this tool call is a web-search tool call, which is performed by xAI server, NO action needed from the client side
"x_search_tool"
Indicates this tool call is an x-search tool call, which is performed by xAI server, NO action needed from the client side
"code_execution_tool"
Indicates this tool call is a code-execution tool call, which is performed by xAI server, NO action needed from the client side
"collections_search_tool"
Indicates this tool call is a collections-search tool call, which is performed by xAI server, NO action needed from the client side
"mcp_tool"
Indicates this tool call is an MCP tool call, which is performed by xAI server, NO action needed from the client side
Understanding Token Usage
Agentic requests have unique token usage patterns compared to standard chat completions. Here's how each token field in the usage object is calculated:

completion_tokens
Represents only the final text output of the model - the comprehensive answer returned to the user. This is typically much smaller than you might expect for such rich, research-driven responses, as the agent performs all its intermediate reasoning and tool orchestration internally.

prompt_tokens
Represents the cumulative input tokens across all inference requests made during the agentic process. Since agentic workflows involve multiple reasoning steps with tool calls, the model makes several inference requests throughout the research process. Each request includes the full conversation history up to that point, which grows as the agent progresses through its research.

While this can result in higher 
prompt_tokens
 counts, agentic requests benefit significantly from prompt caching. The majority of the prompt (the conversation prefix) remains unchanged between inference steps, allowing for efficient caching of the shared context. This means that while the total 
prompt_tokens
 may appear high, much of the computation is optimized through intelligent caching of the stable conversation history, leading to better cost efficiency overall.

reasoning_tokens
Represents the tokens used for the model's internal reasoning process during agentic workflows. This includes the computational work the agent performs to plan tool calls, analyze results, and formulate responses, but excludes the final output tokens.

cached_prompt_text_tokens
Indicates how many prompt tokens were served from cache rather than recomputed. This shows the efficiency gains from prompt caching - higher values indicate better cache utilization and lower costs.

prompt_image_tokens
Represents the tokens derived from visual content that the agent processes during the request. These tokens are produced when visual understanding is enabled and the agent views images (e.g., via web browsing) or analyzes video frames on X. They are counted separately from text tokens and reflect the cost of ingesting visual features alongside the textual context. If no images or videos are processed, this value will be zero.

prompt_text_tokens
 and 
total_tokens
prompt_text_tokens
 reflects the actual text tokens in prompts (excluding any special tokens), while 
total_tokens
 is the sum of all token types used in the request.

Synchronous Agentic Requests (Non-streaming)
Although not typically recommended, for simpler use cases or when you want to wait for the complete agentic workflow to finish before processing the response, you can use synchronous requests:

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import code_execution, web_search, x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        web_search(),
        x_search(),
        code_execution(),
    ],
)
chat.append(user("What is the latest update from xAI?"))
# Get the final response in one go once it's ready
response = chat.sample()
print("\n\nFinal Response:")
print(response.content)
# Access the citations of the final response
print("\n\nCitations:")
print(response.citations)
# Access the usage details from the entire search process
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
# Access the server side tool calls of the final response
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
Synchronous requests will wait for the entire agentic process to complete before returning the response. This is simpler for basic use cases but provides less visibility into the intermediate steps compared to streaming.

Using Tools with OpenAI Responses API
We also support using the OpenAI Responses API in both streaming and non-streaming modes.

Python

import os
import requests
url = "https://api.x.ai/v1/responses"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {os.getenv('XAI_API_KEY')}"
}
payload = {
    "model": "grok-4-fast",
    "input": [
        {
            "role": "user",
            "content": "what is the latest update from xAI?"
        }
    ],
    "tools": [
        {
            "type": "web_search"
        },
        {
            "type": "x_search"
        }
    ]
}
response = requests.post(url, headers=headers, json=payload)
print(response.json())
Identifying the Client-side Tool Call
A critical step in mixing server-side tools and client-side tools is to identify whether a returned tool call is a client-side tool that needs to be executed locally on the client side.

Similar to the way in xAI Python SDK, you can identify the client-side tool call by checking the 
type
 of the output entries (
response.output[].type
) in the response of OpenAI Responses API.

Types	Description
"function_call"
Indicates this tool call is a client-side tool call, and an invocation to this function on the client side is required and the tool output needs to be appended to the chat
"web_search_call"
Indicates this tool call is a web-search tool call, which is performed by xAI server, NO action needed from the client side
"x_search_call"
Indicates this tool call is an x-search tool call, which is performed by xAI server, NO action needed from the client side
"code_interpreter_call"
Indicates this tool call is a code-execution tool call, which is performed by xAI server, NO action needed from the client side
"file_search_call"
Indicates this tool call is a collections-search tool call, which is performed by xAI server, NO action needed from the client side
"mcp_call"
Indicates this tool call is an MCP tool call, which is performed by xAI server, NO action needed from the client side
Agentic Tool Calling Requirements and Limitations
Model Compatibility
Supported Models: 
grok-4
, 
grok-4-fast
, 
grok-4-fast-non-reasoning
Strongly Recommended: 
grok-4-fast
 - specifically trained to excel at agentic tool calling
Request Constraints
No batch requests: 
n > 1
 not supported
No response format: Structured output not yet available with agentic tool calling
Limited sampling params: Only 
temperature
 and 
top_p
 are respected
Note: These constraints may be relaxed in future releases based on user feedback.

FAQ and Troubleshooting
I'm seeing empty or incorrect content when using agentic tool calling with the xAI Python SDK
Please make sure to upgrade to the latest version of the xAI SDK. Agentic tool calling requires version 
1.3.1
 or above.

 Search Tools
Agentic search represents one of the most compelling applications of agentic tool calling, with 
grok-4-fast
 specifically trained to excel in this domain. Leveraging its speed and reasoning capabilities, the model iteratively calls search tools—analyzing responses and making follow-up queries as needed—to seamlessly navigate web pages and X posts, uncovering difficult-to-find information or insights that would otherwise require extensive human analysis.

xAI Python SDK Users: Version 1.3.1 of the xai-sdk package is required to use the agentic tool calling API.

Available Search Tools
You can use the following server-side search tools in your request:

Web Search - allows the agent to search the web and browse pages
X Search - allows the agent to perform keyword search, semantic search, user search, and thread fetch on X
You can customize which tools are enabled in a given request by listing the needed tools in the 
tools
 parameter in the request.

Tool	xAI SDK	OpenAI Responses API
Web Search	
web_search
web_search
X Search	
x_search
x_search
Retrieving Citations
Citations provide traceability for sources used during agentic search. Access them from the response object:


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[web_search()],
)
chat.append(user("What is xAI?"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
As mentioned in the overview page, the citations array contains the URLs of all sources the agent encountered during its search process, meaning that not every URL here will necessarily be relevant to the final answer, as the agent may examine a particular source and determine it is not sufficiently relevant to the user's original query.

For complete details on citations, including when they're available and usage notes, see the overview page.

Applying Search Filters to Control Agentic Search
Each search tool supports a set of optional search parameters to help you narrow down the search space and limit the sources/information the agent is exposed to during its search process.

Tool	Supported Filter Parameters
Web Search	
allowed_domains
, 
excluded_domains
, 
enable_image_understanding
X Search	
allowed_x_handles
, 
excluded_x_handles
, 
from_date
, 
to_date
, 
enable_image_understanding
, 
enable_video_understanding
Web Search Parameters
Only Search in Specific Domains
Use 
allowed_domains
 to make the web search only perform the search and web browsing on web pages that fall within the specified domains.

allowed_domains
 can include a maximum of five domains.

allowed_domains
 cannot be set together with 
excluded_domains
 in the same request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        web_search(allowed_domains=["wikipedia.org"]),
    ],
)
chat.append(user("What is xAI?"))
# stream or sample the response...
Exclude Specific Domains
Use 
excluded_domains
 to prevent the model from including the specified domains in any web search tool invocations and from browsing any pages on those domains.

excluded_domains
 can include a maximum of five domains.

excluded_domains
 cannot be set together with 
allowed_domains
 in the same request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        web_search(excluded_domains=["wikipedia.org"]),
    ],
)
chat.append(user("What is xAI?"))
# stream or sample the response...
Enable Image Understanding
Setting 
enable_image_understanding
 to true equips the agent with access to the 
view_image
 tool, allowing it to invoke this tool on any image URLs encountered during the search process. The model can then interpret and analyze image contents, incorporating this visual information into its context to potentially influence the trajectory of follow-up tool calls.

When the model invokes this tool, you will see it as an entry in 
chunk.tool_calls
 and 
response.tool_calls
 with the 
image_url
 as a parameter. Additionally, 
SERVER_SIDE_TOOL_VIEW_IMAGE
 will appear in 
response.server_side_tool_usage
 along with the number of times it was called when using the xAI Python SDK.

Note that enabling this feature increases token usage, as images are processed and represented as image tokens in the model's context.

Enabling this parameter for Web Search will also enable the image understanding for X Search tool if it's also included in the request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        web_search(enable_image_understanding=True),
    ],
)
chat.append(user("What is included in the image in xAI's official website?"))
# stream or sample the response...
X Search Parameters
Only Consider X Posts from Specific Handles
Use 
allowed_x_handles
 to consider X posts only from a given list of X handles. The maximum number of handles you can include is 10.

allowed_x_handles
 cannot be set together with 
excluded_x_handles
 in the same request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        x_search(allowed_x_handles=["elonmusk"]),
    ],
)
chat.append(user("What is the current status of xAI?"))
# stream or sample the response...
Exclude X Posts from Specific Handles
Use 
excluded_x_handles
 to prevent the model from including X posts from the specified handles in any X search tool invocations. The maximum number of handles you can exclude is 10.

excluded_x_handles
 cannot be set together with 
allowed_x_handles
 in the same request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        x_search(excluded_x_handles=["elonmusk"]),
    ],
)
chat.append(user("What is the current status of xAI?"))
# stream or sample the response...
Date Range
You can restrict the date range of search data used by specifying 
from_date
 and 
to_date
. This limits the data to the period from 
from_date
 to 
to_date
, including both dates.

Both fields need to be in ISO8601 format, e.g., "YYYY-MM-DD". If you're using the xAI Python SDK, the 
from_date
 and 
to_date
 fields can be passed as 
datetime.datetime
 objects.

The fields can also be used independently. With only 
from_date
 specified, the data used will be from the 
from_date
 to today, and with only 
to_date
 specified, the data used will be all data until the 
to_date
.


Python
Other

import os
from datetime import datetime
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        x_search(
            from_date=datetime(2025, 10, 1),
            to_date=datetime(2025, 10, 10),
        ),
    ],
)
chat.append(user("What is the current status of xAI?"))
# stream or sample the response...
Enable Image Understanding
Setting 
enable_image_understanding
 to true equips the agent with access to the 
view_image
 tool, allowing it to invoke this tool on any image URLs encountered during the search process. The model can then interpret and analyze image contents, incorporating this visual information into its context to potentially influence the trajectory of follow-up tool calls.

When the model invokes this tool, you will see it as an entry in 
chunk.tool_calls
 and 
response.tool_calls
 with the 
image_url
 as a parameter. Additionally, 
SERVER_SIDE_TOOL_VIEW_IMAGE
 will appear in 
response.server_side_tool_usage
 along with the number of times it was called when using the xAI Python SDK.

Note that enabling this feature increases token usage, as images are processed and represented as image tokens in the model's context.

Enabling this parameter for X Search will also enable the image understanding for Web Search tool if it's also included in the request.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        x_search(enable_image_understanding=True),
    ],
)
chat.append(user("What images are being shared in recent xAI posts?"))
# stream or sample the response...
Enable Video Understanding
Setting 
enable_video_understanding
 to true equips the agent with access to the 
view_x_video
 tool, allowing it to invoke this tool on any video URLs encountered in X posts during the search process. The model can then analyze video content, incorporating this information into its context to potentially influence the trajectory of follow-up tool calls.

When the model invokes this tool, you will see it as an entry in 
chunk.tool_calls
 and 
response.tool_calls
 with the 
video_url
 as a parameter. Additionally, 
SERVER_SIDE_TOOL_VIEW_X_VIDEO
 will appear in 
response.server_side_tool_usage
 along with the number of times it was called when using the xAI Python SDK.

Note that enabling this feature increases token usage, as video content is processed and represented as tokens in the model's context.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        x_search(enable_video_understanding=True),
    ],
)
chat.append(user("What is the latest video talking about from the xAI official X account?"))
# stream or sample the response...

Code Execution Tool
The code execution tool enables Grok to write and execute Python code in real-time, dramatically expanding its capabilities beyond text generation. This powerful feature allows Grok to perform precise calculations, complex data analysis, statistical computations, and solve mathematical problems that would be impossible through text alone.

xAI Python SDK Users: Version 1.3.1 of the xai-sdk package is required to use the agentic tool calling API.

Vercel AI SDK Support: The code execution tool is not yet supported in the Vercel AI SDK. Please use the xAI SDK or OpenAI SDK for this functionality.

Key Capabilities
Mathematical Computations: Solve complex equations, perform statistical analysis, and handle numerical calculations with precision
Data Analysis: Process datasets, and extract insights from the prompt
Financial Modeling: Build financial models, calculate risk metrics, and perform quantitative analysis
Scientific Computing: Handle scientific calculations, simulations, and data transformations
Code Generation & Testing: Write, test, and debug Python code snippets in real-time
When to Use Code Execution
The code execution tool is particularly valuable for:

Numerical Problems: When you need exact calculations rather than approximations
Data Processing: Analyzing complex data from the prompt
Complex Logic: Multi-step calculations that require intermediate results
Verification: Double-checking mathematical results or validating assumptions
SDK Support
The code execution tool is available across multiple SDKs and APIs with different naming conventions:

SDK/API	Tool Name	Description
xAI SDK	
code_execution
Native xAI SDK implementation
OpenAI Responses API	
code_interpreter
Compatible with OpenAI's API format
Implementation Example
Below are comprehensive examples showing how to integrate the code execution tool across different platforms and use cases.

Basic Calculations

Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import code_execution
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[code_execution()],
)
# Ask for a mathematical calculation
chat.append(user("Calculate the compound interest for $10,000 at 5% annually for 10 years"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
Data Analysis
Python


import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import code_execution
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Multi-turn conversation with data analysis
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[code_execution()],
)
# Step 1: Load and analyze data
chat.append(user("""
I have sales data for Q1-Q4: [120000, 135000, 98000, 156000].
Please analyze this data and create a visualization showing:
1. Quarterly trends
2. Growth rates
3. Statistical summary
"""))
print("##### Step 1: Data Analysis #####\n")
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nAnalysis Results:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
chat.append(response)
# Step 2: Follow-up analysis
chat.append(user("Now predict Q1 next year using linear regression"))
print("\n\n##### Step 2: Prediction Analysis #####\n")
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nPrediction Results:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
Best Practices
1. Be Specific in Requests
Provide clear, detailed instructions about what you want the code to accomplish:

Python


# Good: Specific and clear
"Calculate the correlation matrix for these variables and highlight correlations above 0.7"
# Avoid: Vague requests  
"Analyze this data"
2. Provide Context and Data Format
Always specify the data format and any constraints on the data, and provide as much context as possible:

Python


# Good: Includes data format and requirements
"""
Here's my CSV data with columns: date, revenue, costs
Please calculate monthly profit margins and identify the best-performing month.
Data: [['2024-01', 50000, 35000], ['2024-02', 55000, 38000], ...]
"""
3. Use Appropriate Model Settings
Temperature: Use lower values (0.0-0.3) for mathematical calculations
Model: Use reasoning models like 
grok-4-fast
 for better code generation
Common Use Cases
Financial Analysis
Python


# Portfolio optimization, risk calculations, option pricing
"Calculate the Sharpe ratio for a portfolio with returns [0.12, 0.08, -0.03, 0.15] and risk-free rate 0.02"
Statistical Analysis
Python


# Hypothesis testing, regression analysis, probability distributions
"Perform a t-test to compare these two groups and interpret the p-value: Group A: [23, 25, 28, 30], Group B: [20, 22, 24, 26]"
Scientific Computing
Python


# Simulations, numerical methods, equation solving
"Solve this differential equation using numerical methods: dy/dx = x^2 + y, with initial condition y(0) = 1"
Limitations and Considerations
Execution Environment: Code runs in a sandboxed Python environment with common libraries pre-installed
Time Limits: Complex computations may have execution time constraints
Memory Usage: Large datasets might hit memory limitations
Package Availability: Most popular Python packages (NumPy, Pandas, Matplotlib, SciPy) are available
File I/O: Limited file system access for security reasons
Security Notes
Code execution happens in a secure, isolated environment
No access to external networks or file systems
Temporary execution context that doesn't persist between requests
All computations are stateless and secure

Collections Search Tool
The collections search tool enables Grok to search through your uploaded knowledge bases (collections), allowing it to retrieve relevant information from your documents to provide more accurate and contextually relevant responses. This tool is particularly powerful when combined with web search capabilities, allowing Grok to autonomously blend your proprietary knowledge with real-time web information to tackle complex research tasks.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use this collections-search tool in the agentic tool calling API.

Key Capabilities
Document Retrieval: Search across uploaded files and collections to find relevant information
Semantic Search: Find documents based on meaning and context, not just keywords
Knowledge Base Integration: Seamlessly integrate your proprietary data with Grok's reasoning
RAG Applications: Power retrieval-augmented generation workflows
Multi-format Support: Search across PDFs, text files, CSVs, and other supported formats
For an introduction to Collections, please check out the Collections documentation.

When to Use Collections Search
The collections search tool is particularly valuable for:

Enterprise Knowledge Bases: When you need Grok to reference internal documents and policies
Customer Support: Building chatbots that can answer questions based on your product documentation
Compliance & Legal: Ensuring responses are grounded in your official guidelines and regulations
Personal Knowledge Management: Organizing and querying your personal document collections
SDK Support
The collections search tool is available across multiple SDKs and APIs with different naming conventions:

SDK/API	Tool Name	Description
xAI SDK	
collections_search
Native xAI SDK implementation
OpenAI Responses API	
file_search
Compatible with OpenAI's API format
Implementation Example
Prerequisites
Before using the collections search tool, you need to first create a collection and upload some documents to it.

For more details, please check out the guide on using collections.

Search in Collections
The example below assumes you have already created a collection and uploaded some documents to it.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import collections_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
      collections_search(
        collection_ids=["collection_id1", "collection_id2"],
        limit=6,
      ),
    ],
)
# Search for a guide among the internal knowledge base.
chat.append(user("How to set up my direct deposit account in payroll?"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)

Remote MCP Tools
Remote MCP Tools allow Grok to connect to external MCP (Model Context Protocol) servers, extending its capabilities with custom tools from third parties or your own implementations. Simply specify a server URL and optional configuration - xAI manages the MCP server connection and interaction on your behalf.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use Remote MCP Tools.

SDK Support
Remote MCP tools are supported in the xAI native SDK and the OpenAI compatible Responses API.

The 
require_approval
 and 
connector_id
 parameters in the OpenAI Responses API are not currently supported.

Configuration
To use remote MCP tools, you need to configure the connection to your MCP server in the tools array of your request.

Parameter	Required	Description
server_url
Yes	The URL of the MCP server to connect to. Only Streaming HTTP and SSE transports are supported.
server_label
No	A label to identify the server (used for tool call prefixing)
server_description
No	A description of what the server provides
allowed_tool_names
No	List of specific tool names to allow (empty allows all)
authorization
No	A token that will be set in the Authorization header on requests to the MCP server
extra_headers
No	Additional headers to include in requests
Basic MCP Tool Usage

Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import mcp
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",
    tools=[
        mcp(server_url="https://mcp.deepwiki.com/mcp"),
    ],
)
chat.append(user("What can you do with https://github.com/xai-org/xai-sdk-python?"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
Tool Enablement and Access Control
When you configure a Remote MCP Tool without specifying 
allowed_tool_names
, all tool definitions exposed by the MCP server are automatically injected into the model's context. This means the model gains access to every tool that the MCP server provides, allowing it to use any of them during the conversation.

For example, if an MCP server exposes 10 different tools and you don't specify 
allowed_tool_names
, all 10 tool definitions will be available to the model. The model can then choose to call any of these tools based on the user's request and the tool descriptions.

Use the 
allowed_tool_names
 parameter to selectively enable only specific tools from an MCP server. This can give you several key benefits:

Better Performance: Reduce context overhead by limiting tool definitions the model needs to consider
Reduced Risk: For example, restrict access to tools that only perform read-only operations to prevent the model from modifying data
Python


# Enable only specific tools from a server with many available tools
mcp(
    server_url="https://comprehensive-tools.example.com/mcp",
    allowed_tool_names=["search_database", "format_data"]
)
Instead of giving the model access to every tool the server offers, this approach keeps Grok focused and efficient while ensuring it has exactly the capabilities it needs.

Multi-Server Support
Enable multiple MCP servers simultaneously to create a rich ecosystem of specialized tools:

Python


chat = client.chat.create(
    model="grok-4-fast",
    tools=[
        mcp(server_url="https://mcp.deepwiki.com/mcp", server_label="deepwiki"),
        mcp(server_url="https://your-custom-tools.com/mcp", server_label="custom"),
        mcp(server_url="https://api.example.com/tools", server_label="api-tools"),
    ],
)
Each server can provide different capabilities - documentation tools, API integrations, custom business logic, or specialized data processing - all accessible within a single conversation.

Best Practices
Provide clear server metadata: Use descriptive 
server_label
 and 
server_description
 when configuring multiple MCP servers to help the model understand each server's purpose and select the right tools
Filter tools appropriately: Use 
allowed_tool_names
 to restrict access to only necessary tools, especially when servers have many tools since the model must keep all available tool definitions in context
Use secure connections: Always use HTTPS URLs and implement proper authentication mechanisms on your MCP server
Provide Examples: While the model can generally figure out what tools to use based on the tool descriptions and the user request it may help to provide examples in the prompt

Advanced Usage
In this section, we explore advanced usage patterns for agentic tool calling, including:

Use Client-side Tools - Combine server-side agentic tools with your own client-side tools for specialized functionality that requires local execution.
Multi-turn Conversations - Maintain context across multiple turns in agentic tool-enabled conversations, allowing the model to build upon previous research and tool results for more complex, iterative problem-solving
Requests with Multiple Active Tools - Send requests with multiple server-side tools active simultaneously, enabling comprehensive analysis with web search, X search, and code execution tools working together
Image Integration - Include images in your tool-enabled conversations for visual analysis and context-aware searches
xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use some advanced capabilities in the agentic tool calling API, for example, the client-side tools.

Vercel AI SDK Support: Advanced tool usage patterns are not yet supported in the Vercel AI SDK. Please use the xAI SDK or OpenAI SDK for this functionality.

Mixing Server-Side and Client-Side Tools
You can combine server-side agentic tools (like web search and code execution) with custom client-side tools to create powerful hybrid workflows. This approach lets you leverage the model's reasoning capabilities with server-side tools while adding specialized functionality that runs locally in your application.

How It Works
The key difference when mixing server-side and client-side tools is that server-side tools are executed automatically by xAI, while client-side tools require developer intervention:

Define your client-side tools using standard function calling patterns
Include both server-side and client-side tools in your request
xAI automatically executes any server-side tools the model decides to use (web search, code execution, etc.)
When the model calls client-side tools, execution pauses - xAI returns the tool calls to you instead of executing them
Detect and execute client-side tool calls yourself, then append the results back to continue the conversation
Repeat this process until the model generates a final response with no additional client-side tool calls
Practical Example
Given a local client-side function 
get_weather
 to get the weather of a specified city, the model can use this client-side tool and the web-search tool to determine the weather in the base city of the 2025 NBA champion.

Using the xAI SDK
You can determine whether a tool call is a client-side tool call by using 
xai_sdk.tools.get_tool_call_type
 against a tool call from the 
response.tool_calls
 list. For more details, check this out.

Import the dependencies, and define the client-side tool.

Python


import os
import json
from xai_sdk import Client
from xai_sdk.chat import user, tool, tool_result
from xai_sdk.tools import web_search, get_tool_call_type
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Define client-side tool
def get_weather(city: str) -> str:
    """Get the weather for a given city."""
    # In a real app, this would query your database
    return f"The weather in {city} is sunny."
# Tools array with both server-side and client-side tools
tools = [
    web_search(),
    tool(
        name="get_weather",
        description="Get the weather for a given city.",
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city",
                }
            },
            "required": ["city"]
        },
    ),
]
model = "grok-4-fast"
Perform the tool loop with conversation continuation:

You can either use 
previous_response_id
 to continue the conversation from the last response.

Python


# Create chat with both server-side and client-side tools
chat = client.chat.create(
    model=model,
    tools=tools,
    store_messages=True,
)
chat.append(
    user(
        "What is the weather in the base city of the team that won the "
        "2025 NBA championship?"
    )
)
while True:
    client_side_tool_calls = []
    for response, chunk in chat.stream():
        for tool_call in chunk.tool_calls:
            if get_tool_call_type(tool_call) == "client_side_tool":
                client_side_tool_calls.append(tool_call)
            else:
                print(
                    f"Server-side tool call: {tool_call.function.name} "
                    f"with arguments: {tool_call.function.arguments}"
                )
    if not client_side_tool_calls:
        break
    chat = client.chat.create(
        model=model,
        tools=tools,
        store_messages=True,
        previous_response_id=response.id,
    )
    for tool_call in client_side_tool_calls:
        print(
            f"Client-side tool call: {tool_call.function.name} "
            f"with arguments: {tool_call.function.arguments}"
        )
        args = json.loads(tool_call.function.arguments)
        result = get_weather(args["city"])
        chat.append(tool_result(result))
print(f"Final response: {response.content}")
Alternatively, you can use the encrypted content to continue the conversation.

Python


# Create chat with both server-side and client-side tools
chat = client.chat.create(
    model=model,
    tools=tools,
    use_encrypted_content=True,
)
chat.append(
    user(
        "What is the weather in the base city of the team that won the "
        "2025 NBA championship?"
    )
)
while True:
    client_side_tool_calls = []
    for response, chunk in chat.stream():
        for tool_call in chunk.tool_calls:
            if get_tool_call_type(tool_call) == "client_side_tool":
                client_side_tool_calls.append(tool_call)
            else:
                print(
                    f"Server-side tool call: {tool_call.function.name} "
                    f"with arguments: {tool_call.function.arguments}"
                )
    chat.append(response)
    if not client_side_tool_calls:
        break
    for tool_call in client_side_tool_calls:
        print(
            f"Client-side tool call: {tool_call.function.name} "
            f"with arguments: {tool_call.function.arguments}"
        )
        args = json.loads(tool_call.function.arguments)
        result = get_weather(args["city"])
        chat.append(tool_result(result))
print(f"Final response: {response.content}")
You will see an output similar to the following:

Text


Server-side tool call: web_search with arguments: {"query":"Who won the 2025 NBA championship?","num_results":5}
Client-side tool call: get_weather with arguments: {"city":"Oklahoma City"}
Final response: The Oklahoma City Thunder won the 2025 NBA championship. The current weather in Oklahoma City is sunny.
Using the OpenAI SDK
You can determine whether a tool call is a client-side tool call by checking the 
type
 field of an output entry from the 
response.output
 list. For more details, please check this out.

Import the dependencies, and define the client-side tool.

Python (OpenAI)


import os
import json
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)
# Define client-side tool
def get_weather(city: str) -> str:
    """Get the weather for a given city."""
    # In a real app, this would query your database
    return f"The weather in {city} is sunny."
model = "grok-4-fast"
tools = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the weather for a given city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city",
                },
            },
            "required": ["city"],
        },
    },
    {
        "type": "web_search",
    },
]
Perform the tool loop:

You can either use 
previous_response_id
.

Python (OpenAI)


response = client.responses.create(
    model=model,
    input=(
        "What is the weather in the base city of the team that won the "
        "2025 NBA championship?"
    ),
    tools=tools,
)
while True:
    tool_outputs = []
    for item in response.output:
        if item.type == "function_call":
            print(f"Client-side tool call: {item.name} with arguments: {item.arguments}")
            args = json.loads(item.arguments)
            weather = get_weather(args["city"])
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": weather,
                }
            )
        elif item.type in (
            "web_search_call",
            "x_search_call", 
            "code_interpreter_call",
            "file_search_call",
            "mcp_call"
        ):
            print(
                f"Server-side tool call: {item.name} with arguments: {item.arguments}"
            )
    if not tool_outputs:
        break
    response = client.responses.create(
        model=model,
        tools=tools,
        input=tool_outputs,
        previous_response_id=response.id,
    )
print("Final response:", response.output[-1].content[0].text)
or using the encrypted content

Python (OpenAI)


input_list = [
    {
        "role": "user",
        "content": (
            "What is the weather in the base city of the team that won the "
            "2025 NBA championship?"
        ),
    }
]
response = client.responses.create(
    model=model,
    input=input_list,
    tools=tools,
    include=["reasoning.encrypted_content"],
)
while True:
    input_list.extend(response.output)
    tool_outputs = []
    for item in response.output:
        if item.type == "function_call":
            print(f"Client-side tool call: {item.name} with arguments: {item.arguments}")
            args = json.loads(item.arguments)
            weather = get_weather(args["city"])
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": weather,
                }
            )
        elif item.type in (
            "web_search_call",
            "x_search_call", 
            "code_interpreter_call",
            "file_search_call",
            "mcp_call"
        ):
            print(
                f"Server-side tool call: {item.name} with arguments: {item.arguments}"
            )
    if not tool_outputs:
        break
    input_list.extend(tool_outputs)
    response = client.responses.create(
        model=model,
        input=input_list,
        tools=tools,
        include=["reasoning.encrypted_content"],
    )
print("Final response:", response.output[-1].content[0].text)
Multi-turn Conversations with Preservation of Agentic State
When using agentic tools, you may want to have multi-turn conversations where follow-up prompts maintain all agentic state, including the full history of reasoning, tool calls, and tool responses. This is possible using the stateful API, which provides seamless integration for preserving conversation context across multiple interactions. There are two options to achieve this outlined below.

Store the Conversation History Remotely
You can choose to store the conversation history remotely on the xAI server, and every time you want to continue the conversation, you can pick up from the last response where you want to resume from.

There are only 2 extra steps:

Add the parameter 
store_messages=True
 when making the first agentic request. This tells the service to store the entire conversation history on xAI servers, including the model's reasoning, server-side tool calls, and corresponding responses.
Pass 
previous_response_id=response.id
 when creating the follow-up conversation, where 
response
 is the response returned by 
chat.sample()
 or 
chat.stream()
 from the conversation that you wish to continue.
Note that the follow-up conversation does not need to use the same tools, model parameters, or any other configuration as the initial conversation—it will still be fully hydrated with the complete agentic state from the previous interaction.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search, x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
# First turn.
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[web_search(), x_search()],
    store_messages=True,
)
chat.append(user("What is xAI?"))
print("\n\n##### First turn #####\n")
for response, chunk in chat.stream():
    print(chunk.content, end="", flush=True)
print("\n\nUsage for first turn:", response.server_side_tool_usage)
# Second turn.
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[web_search(), x_search()],
    # pass the response id of the first turn to continue the conversation
    previous_response_id=response.id,
)
chat.append(user("What is its latest mission?"))
print("\n\n##### Second turn #####\n")
for response, chunk in chat.stream():
    print(chunk.content, end="", flush=True)
print("\n\nUsage for second turn:", response.server_side_tool_usage)
Append the Encrypted Agentic Tool Calling States
There is another option for the ZDR (Zero Data Retention) users, or the users who don't want to use the above option, that is to let the xAI server also return the encrypted reasoning and the encrypted tool output besides the final content to the client side, and those encrypted contents can be included as a part of the context in the next turn conversation.

Here are the extra steps you need to take for this option:

Add the parameter 
use_encrypted_content=True
 when making the first agentic request. This tells the service to return the entire conversation history to the client side, including the model's reasoning (encrypted), server-side tool calls, and corresponding responses (encrypted).
Append the response to the conversation you wish to continue before making the call to 
chat.sample()
 or 
chat.stream()
.
Python


import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search, x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
# First turn.
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[web_search(), x_search()],
    use_encrypted_content=True,
)
chat.append(user("What is xAI?"))
print("\n\n##### First turn #####\n")
for response, chunk in chat.stream():
    print(chunk.content, end="", flush=True)
print("\n\nUsage for first turn:", response.server_side_tool_usage)
chat.append(response)
print("\n\n##### Second turn #####\n")
chat.append(user("What is its latest mission?"))
# Second turn.
for response, chunk in chat.stream():
    print(chunk.content, end="", flush=True)
print("\n\nUsage for second turn:", response.server_side_tool_usage)
For more details about stateful responses, please check out this guide.

Tool Combinations
Equipping your requests with multiple tools is straightforward—simply include the tools you want to activate in the 
tools
 array of your request. The model will intelligently orchestrate between them based on the task at hand.

Suggested Tool Combinations
Here are some common patterns for combining tools, depending on your use case:

If you're trying to...	Consider activating...	Because...
Research & analyze data	Web Search + Code Execution	Web search gathers information, code execution analyzes and visualizes it
Aggregate news & social media	Web Search + X Search	Get comprehensive coverage from both traditional web and social platforms
Extract insights from multiple sources	Web Search + X Search + Code Execution	Collect data from various sources then compute correlations and trends
Monitor real-time discussions	X Search + Web Search	Track social sentiment alongside authoritative information

Python
Other

from xai_sdk.tools import web_search, x_search, code_execution
# Example tool combinations for different scenarios
research_setup = [web_search(), code_execution()]
news_setup = [web_search(), x_search()]
comprehensive_setup = [web_search(), x_search(), code_execution()]
Using Tool Combinations in Different Scenarios
When you want to search for news on the Internet, you can activate all search tools:
Web search tool
X search tool

Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search, x_search
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[
        web_search(),
        x_search(),
    ],
)
chat.append(user("what is the latest update from xAI?"))
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)
When you want to collect up-to-date data from the Internet and perform calculations based on the Internet data, you can choose to activate:
Web search tool
Code execution tool

Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import web_search, code_execution
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    # research_tools
    tools=[
        web_search(),
        code_execution(),
    ],
)
chat.append(user("What is the average market cap of the companies with the top 5 market cap in the US stock market today?"))
# sample or stream the response...
Using Images in the Context
You can bootstrap your requests with an initial conversation context that includes images.

In the code sample below, we pass an image into the context of the conversation before initiating an agentic request.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import image, user
from xai_sdk.tools import web_search, x_search
# Create the client and define the server-side tools to use
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4-fast",  # reasoning model
    tools=[web_search(), x_search()],
)
# Add an image to the conversation
chat.append(
    user(
        "Search the internet and tell me what kind of dog is in the image below.",
        "And what is the typical lifespan of this dog breed?",
        image(
            "https://pbs.twimg.com/media/G3B7SweXsAAgv5N?format=jpg&name=900x900"
        ),
    )
)
is_thinking = True
for response, chunk in chat.stream():
    # View the server-side tool calls as they are being made in real-time
    for tool_call in chunk.tool_calls:
        print(f"\nCalling tool: {tool_call.function.name} with arguments: {tool_call.function.arguments}")
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    if chunk.content and is_thinking:
        print("\n\nFinal Response:")
        is_thinking = False
    if chunk.content and not is_thinking:
        print(chunk.content, end="", flush=True)
print("\n\nCitations:")
print(response.citations)
print("\n\nUsage:")
print(response.usage)
print(response.server_side_tool_usage)
print("\n\nServer Side Tool Calls:")
print(response.tool_calls)

Files
The Files API enables you to upload documents and use them in chat conversations with Grok. When you attach files to a chat message, the system automatically activates the 
document_search
 tool, transforming your request into an agentic workflow where Grok can intelligently search through and reason over your documents to answer questions.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use the Files API.

How Files Work with Chat
Behind the scenes, when you attach files to a chat message, the xAI API implicitly adds the 
document_search
 server-side tool to your request. This means:

Automatic Agentic Behavior: Your chat request becomes an agentic request, where Grok autonomously searches through your documents
Intelligent Document Analysis: The model can reason over document content, extract relevant information, and synthesize answers
Multi-Document Support: You can attach multiple files, and Grok will search across all of them
This seamless integration allows you to simply attach files and ask questions—the complexity of document search and retrieval is handled automatically by the agentic workflow.

Understanding Document Search
When you attach files to a chat message, the xAI API automatically activates the 
document_search
 server-side tool. This transforms your request into an agentic workflow where Grok:

Analyzes your query to understand what information you're seeking
Searches the documents intelligently, finding relevant sections across all attached files
Extracts and synthesizes information from multiple sources if needed
Provides a comprehensive answer with the context from your documents
Agentic Workflow
Just like other agentic tools (web search, X search, code execution), document search operates autonomously:

Multiple searches: The model may search documents multiple times with different queries to find comprehensive information
Reasoning: The model uses its reasoning capabilities to decide what to search for and how to interpret the results
Streaming visibility: In streaming mode, you can see when the model is searching your documents via tool call notifications
Token Usage with Files
File-based chats follow similar token patterns to other agentic requests:

Prompt tokens: Include the conversation history and internal processing. Document content is processed efficiently
Reasoning tokens: Used for planning searches and analyzing document content
Completion tokens: The final answer text
Cached tokens: Repeated document content benefits from prompt caching for efficiency
The actual document content is processed by the server-side tool and doesn't directly appear in the message history, keeping token usage optimized.

Pricing
Document search is billed at $10 per 1,000 tool invocations, in addition to standard token costs. Each time the model searches your documents, it counts as one tool invocation. For complete pricing details, see the Models and Pricing page.

Getting Started
To use files with Grok, you'll need to:

Upload and manage files - Learn how to upload, list, retrieve, and delete files using the Files API
Chat with files - Discover how to attach files to chat messages and ask questions about your documents
Quick Example
Here's a quick example of the complete workflow:

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file
client = Client(api_key=os.getenv("XAI_API_KEY"))
# 1. Upload a document
document_content = b"""Quarterly Sales Report - Q4 2024
Total Revenue: $5.2M
Growth: +18% YoY
"""
uploaded_file = client.files.upload(document_content, filename="sales.txt")
# 2. Chat with the file
chat = client.chat.create(model="grok-4-fast")
chat.append(user("What was the total revenue?", file(uploaded_file.id)))
# 3. Get the answer
response = chat.sample()
print(response.content)  # "The total revenue was $5.2M"
# 4. Clean up
client.files.delete(uploaded_file.id)
Key Features
Multiple File Support
Attach multiple documents to a single query and Grok will search across all of them to find relevant information.

Multi-Turn Conversations
File context persists across conversation turns, allowing you to ask follow-up questions without re-attaching files.

Code Execution Integration
Combine files with the code execution tool to perform advanced data analysis, statistical computations, and transformations on your uploaded data. The model can write and execute Python code that processes your files directly.

Limitations
File size: Maximum 48 MB per file
No batch requests: File attachments with document search are agentic requests and do not support batch mode (
n > 1
)
Agentic models only: Requires models that support agentic tool calling (e.g., 
grok-4-fast
, 
grok-4
)
Supported file formats:
Plain text files (.txt)
Markdown files (.md)
Code files (.py, .js, .java, etc.)
CSV files (.csv)
JSON files (.json)
PDF documents (.pdf)
And many other text-based formats

Managing Files
The Files API provides a complete set of operations for managing your files. Before using files in chat conversations, you need to upload them using one of the methods described below.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use the Files API.

Uploading Files
You can upload files in several ways: from a file path, raw bytes, BytesIO object, or an open file handle.

Upload from File Path

Python
Other

import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a file from disk
file = client.files.upload("/path/to/your/document.pdf")
print(f"File ID: {file.id}")
print(f"Filename: {file.filename}")
print(f"Size: {file.size} bytes")
print(f"Created at: {file.created_at}")
Upload from Bytes
Python


import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload file content directly from bytes
content = b"This is my document content.\nIt can span multiple lines."
file = client.files.upload(content, filename="document.txt")
print(f"File ID: {file.id}")
print(f"Filename: {file.filename}")
Upload from file object
Python


import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a file directly from disk
file = client.files.upload(open("document.pdf", "rb"), filename="document.pdf")
print(f"File ID: {file.id}")
print(f"Filename: {file.filename}")
Upload Progress Tracking
Track upload progress for large files using callbacks or progress bars.

Custom Progress Callback
Python


import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Define a custom progress callback
def progress_callback(bytes_uploaded: int, total_bytes: int):
    percentage = (bytes_uploaded / total_bytes) * 100 if total_bytes else 0
    mb_uploaded = bytes_uploaded / (1024 * 1024)
    mb_total = total_bytes / (1024 * 1024)
    print(f"Progress: {mb_uploaded:.2f}/{mb_total:.2f} MB ({percentage:.1f}%)")
# Upload with progress tracking
file = client.files.upload(
    "/path/to/large-file.pdf",
    on_progress=progress_callback
)
print(f"Successfully uploaded: {file.filename}")
Progress Bar with tqdm
Python


import os
from xai_sdk import Client
from tqdm import tqdm
client = Client(api_key=os.getenv("XAI_API_KEY"))
file_path = "/path/to/large-file.pdf"
total_bytes = os.path.getsize(file_path)
# Upload with tqdm progress bar
with tqdm(total=total_bytes, unit="B", unit_scale=True, desc="Uploading") as pbar:
    file = client.files.upload(
        file_path,
        on_progress=pbar.update
    )
print(f"Successfully uploaded: {file.filename}")
Listing Files
Retrieve a list of your uploaded files with pagination and sorting options.

Available Options
limit
: Maximum number of files to return. If not specified, uses server default of 100.
order
: Sort order for the files. Either 
"asc"
 (ascending) or 
"desc"
 (descending).
sort_by
: Field to sort by. Options: 
"created_at"
, 
"filename"
, or 
"size"
.
pagination_token
: Token for fetching the next page of results.

Python
Other

import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# List files with pagination and sorting
response = client.files.list(
    limit=10,
    order="desc",
    sort_by="created_at"
)
for file in response.data:
    print(f"File: {file.filename} (ID: {file.id}, Size: {file.size} bytes)")
Getting File Metadata
Retrieve detailed information about a specific file.


Python
Other

import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Get file metadata by ID
file = client.files.get("file-abc123")
print(f"Filename: {file.filename}")
print(f"Size: {file.size} bytes")
print(f"Created: {file.created_at}")
print(f"Team ID: {file.team_id}")
Getting File Content
Download the actual content of a file.


Python
Other

import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Get file content
content = client.files.content("file-abc123")
# Content is returned as bytes
print(f"Content length: {len(content)} bytes")
print(f"Content preview: {content[:100]}")
Deleting Files
Remove files when they're no longer needed.


Python
Other

import os
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Delete a file
delete_response = client.files.delete("file-abc123")
print(f"Deleted: {delete_response.deleted}")
print(f"File ID: {delete_response.id}")
Limitations and Considerations
File Size Limits
Maximum file size: 48 MB per file
Processing time: Larger files may take longer to process
File Retention
Cleanup: Delete files when no longer needed to manage storage
Access: Files are scoped to your team/organization
Supported Formats
While many text-based formats are supported, the system works best with:

Structured documents (with clear sections, headings)
Plain text and markdown
Documents with clear information hierarchy
Supported file types include:

Plain text files (.txt)
Markdown files (.md)
Code files (.py, .js, .java, etc.)
CSV files (.csv)
JSON files (.json)
PDF documents (.pdf)
And many other text-based formats
Next Steps
Now that you know how to manage files, learn how to use them in chat conversations:

Chat with Files
Once you've uploaded files, you can reference them in conversations using the 
file()
 helper function in the xAI Python SDK. When files are attached, the system automatically enables document search capabilities, transforming your request into an agentic workflow.

xAI Python SDK Users: Version 1.4.0 of the xai-sdk package is required to use the Files API.

Basic Chat with a Single File
Reference an uploaded file in a conversation to let the model search through it for relevant information.


Python
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, file
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a document
document_content = b"""Quarterly Sales Report - Q4 2024
Revenue Summary:
- Total Revenue: $5.2M
- Year-over-Year Growth: +18%
- Quarter-over-Quarter Growth: +7%
Top Performing Products:
- Product A: $2.1M revenue (+25% YoY)
- Product B: $1.8M revenue (+12% YoY)
- Product C: $1.3M revenue (+15% YoY)
"""
uploaded_file = client.files.upload(document_content, filename="sales_report.txt")
# Create a chat with the file attached
chat = client.chat.create(model="grok-4-fast")
chat.append(user("What was the total revenue in this report?", file(uploaded_file.id)))
# Get the response
response = chat.sample()
print(f"Answer: {response.content}")
print(f"\nUsage: {response.usage}")
# Clean up
client.files.delete(uploaded_file.id)
Streaming Chat with Files
Get real-time responses while the model searches through your documents.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a document
document_content = b"""Product Specifications:
- Model: XR-2000
- Weight: 2.5 kg
- Dimensions: 30cm x 20cm x 10cm
- Power: 100W
- Features: Wireless connectivity, LCD display, Energy efficient
"""
uploaded_file = client.files.upload(document_content, filename="specs.txt")
# Create chat with streaming
chat = client.chat.create(model="grok-4-fast")
chat.append(user("What is the weight of the XR-2000?", file(uploaded_file.id)))
# Stream the response
is_thinking = True
for response, chunk in chat.stream():
    # Show tool calls as they happen
    for tool_call in chunk.tool_calls:
        print(f"\nSearching: {tool_call.function.name}")
    
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    
    if chunk.content and is_thinking:
        print("\n\nAnswer:")
        is_thinking = False
    
    if chunk.content:
        print(chunk.content, end="", flush=True)
print(f"\n\nUsage: {response.usage}")
# Clean up
client.files.delete(uploaded_file.id)
Multiple File Attachments
Query across multiple documents simultaneously.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload multiple documents
file1_content = b"Document 1: The project started in January 2024."
file2_content = b"Document 2: The project budget is $500,000."
file3_content = b"Document 3: The team consists of 5 engineers and 2 designers."
file1 = client.files.upload(file1_content, filename="timeline.txt")
file2 = client.files.upload(file2_content, filename="budget.txt")
file3 = client.files.upload(file3_content, filename="team.txt")
# Create chat with multiple files
chat = client.chat.create(model="grok-4-fast")
chat.append(
    user(
        "Based on these documents, when did the project start, what is the budget, and how many people are on the team?",
        file(file1.id),
        file(file2.id),
        file(file3.id),
    )
)
response = chat.sample()
print(f"Answer: {response.content}")
print("\nDocuments searched: 3")
print(f"Usage: {response.usage}")
# Clean up
client.files.delete(file1.id)
client.files.delete(file2.id)
client.files.delete(file3.id)
Multi-Turn Conversations with Files
Maintain context across multiple questions about the same documents. Use encrypted content to preserve file context efficiently across multiple turns.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload an employee record
document_content = b"""Employee Information:
Name: Alice Johnson
Department: Engineering
Years of Service: 5
Performance Rating: Excellent
Skills: Python, Machine Learning, Cloud Architecture
Current Project: AI Platform Redesign
"""
uploaded_file = client.files.upload(document_content, filename="employee.txt")
# Create a multi-turn conversation with encrypted content
chat = client.chat.create(
    model="grok-4-fast",
    use_encrypted_content=True,  # Enable encrypted content for efficient multi-turn
)
# First turn: Ask about the employee name
chat.append(user("What is the employee's name?", file(uploaded_file.id)))
response1 = chat.sample()
print("Q1: What is the employee's name?")
print(f"A1: {response1.content}\n")
# Add the response to conversation history
chat.append(response1)
# Second turn: Ask about department (agentic context is retained via encrypted content)
chat.append(user("What department does this employee work in?"))
response2 = chat.sample()
print("Q2: What department does this employee work in?")
print(f"A2: {response2.content}\n")
# Add the response to conversation history
chat.append(response2)
# Third turn: Ask about skills
chat.append(user("What skills does this employee have?"))
response3 = chat.sample()
print("Q3: What skills does this employee have?")
print(f"A3: {response3.content}\n")
# Clean up
client.files.delete(uploaded_file.id)
Combining Files with Other Modalities
You can combine file attachments with images and other content types in a single message.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file, image
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a text document with cat care information
text_content = b"Cat Care Guide: Cats require daily grooming, especially long-haired breeds. Regular brushing helps prevent matting and reduces shedding."
text_file = client.files.upload(text_content, filename="cat-care.txt")
# Use both file and image in the same message
chat = client.chat.create(model="grok-4-fast")
chat.append(
    user(
        "Based on the attached care guide, do you have any advice about the pictured cat?",
        file(text_file.id),
        image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/1200px-Cat03.jpg"),
    )
)
response = chat.sample()
print(f"Analysis: {response.content}")
print(f"\nUsage: {response.usage}")
# Clean up
client.files.delete(text_file.id)
Combining Files with Code Execution
For data analysis tasks, you can attach data files and enable the code execution tool. This allows Grok to write and run Python code to analyze and process your data.

Python


import os
from xai_sdk import Client
from xai_sdk.chat import user, file
from xai_sdk.tools import code_execution
client = Client(api_key=os.getenv("XAI_API_KEY"))
# Upload a CSV data file
csv_content = b"""product,region,revenue,units_sold
Product A,North,245000,1200
Product A,South,189000,950
Product A,East,312000,1500
Product A,West,278000,1350
Product B,North,198000,800
Product B,South,156000,650
Product B,East,234000,950
Product B,West,201000,850
Product C,North,167000,700
Product C,South,134000,550
Product C,East,198000,800
Product C,West,176000,725
"""
data_file = client.files.upload(csv_content, filename="sales_data.csv")
# Create chat with both file attachment and code execution
chat = client.chat.create(
    model="grok-4-fast",
    tools=[code_execution()],  # Enable code execution
)
chat.append(
    user(
        "Analyze this sales data and calculate: 1) Total revenue by product, 2) Average units sold by region, 3) Which product-region combination has the highest revenue",
        file(data_file.id)
    )
)
# Stream the response to see code execution in real-time
is_thinking = True
for response, chunk in chat.stream():
    for tool_call in chunk.tool_calls:
        if tool_call.function.name == "code_execution":
            print("\n[Executing Code]")
    
    if response.usage.reasoning_tokens and is_thinking:
        print(f"\rThinking... ({response.usage.reasoning_tokens} tokens)", end="", flush=True)
    
    if chunk.content and is_thinking:
        print("\n\nAnalysis Results:")
        is_thinking = False
    
    if chunk.content:
        print(chunk.content, end="", flush=True)
print(f"\n\nUsage: {response.usage}")
# Clean up
client.files.delete(data_file.id)
The model will:

Access the attached data file
Write Python code to load and analyze the data
Execute the code in a sandboxed environment
Perform calculations and statistical analysis
Return the results and insights in the response
Limitations and Considerations
Request Constraints
No batch requests: File attachments with document search are agentic requests and do not support batch mode (
n > 1
)
Streaming recommended: Use streaming mode for better observability of document search process
Document Complexity
Highly unstructured or very long documents may require more processing
Well-organized documents with clear structure are easier to search
Large documents with many searches can result in higher token usage
Model Compatibility
Recommended models: 
grok-4-fast
, 
grok-4
 for best document understanding
Agentic requirement: File attachments require agentic-capable models that support server-side tools.
Live Search
The advanced agentic search capabilities powering grok.com are generally available in the new agentic tool calling API, and the Live Search API will be deprecated by December 15, 2025.

The chat completion endpoint supports querying live data and considering those in generating responses. With this functionality, instead of orchestrating web search and LLM tool calls yourself, you can get chat responses with live data directly from the API.

Live search is available via the chat completions endpoint. It is turned off by default. Customers have control over the content they access, and we are not liable for any resulting damages or liabilities.

For more details, refer to 
search_parameters
 in API Reference - Chat completions.

For examples on search sources, jump to Data Sources and Parameters.

Live Search Pricing
Live Search costs $25 per 1,000 sources used. That means each source costs $0.025.

The number of sources used can be found in the 
response
 object, which contains a field called 
response.usage.num_sources_used
.

Enabling Search
To enable search, you need to specify in your chat completions request an additional field 
search_parameters
, with 
"mode"
 from one of 
"auto"
, 
"on"
, 
"off"
.

If you want to use Live Search with default values, you still need to specify an empty 
search_parameters
.

JSON


"search_parameters": {}
Or if using xAI Python SDK:

Python


search_parameters=SearchParameters(),
The 
"mode"
 field sets the preference of data source: - 
"off"
: Disables search and uses the model without accessing additional information from data sources. - 
"auto"
 (default): Live search is available to the model, but the model automatically decides whether to perform live search. - 
"on"
: Enables live search.

The model decides which data source to use within the provided data sources, via the 
"sources"
 field in 
"search_parameters"
. If no 
"sources"
 is provided, live search will default to making web and X data available to the model.

For example, you can send the following request, where the model will decide whether to search in data:


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(mode="auto"),
)
chat.append(user("Provide me a digest of world news of the week before July 9, 2025."))
response = chat.sample()
print(response.content)
Returning citations
The live search endpoint supports returning citations to the data sources used in the response in the form of a list of URLs. To enable this, you can set 
"return_citations": true
 in your search parameters. This field defaults to 
true
.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        return_citations=True,
    ),
)
chat.append(user("Provide me a digest of world news on July 9, 2025."))
response = chat.sample()
print(response.content)
print(response.citations)
Streaming behavior with citations
During streaming, you would get the chat response chunks as usual. The citations will be returned as a list of url strings in the field 
"citations"
 only in the last chunk. This is similar to how the usage data is returned with streaming.

Set date range of the search data
You can restrict the date range of search data used by specifying 
"from_date"
 and 
"to_date"
. This limits the data to the period from 
"from_date"
 to 
"to_date"
, including both dates.

Both fields need to be in ISO8601 format, e.g. "YYYY-MM-DD". If you're using the xAI Python SDK, the 
from_date
 and 
to_date
 fields can be passed as 
datetime.datetime
 objects to the 
SearchParameters
 class.

The fields can also be independently used. With only 
"from_date"
 specified, the data used will be from the 
"from_date"
 to today, and with only 
"to_date"
 specified, the data used will be all data till the 
"to_date"
.


Python

Javascript
Other

import os
from datetime import datetime
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters
client = Client(api_key=os.getenv('XAI_API_KEY'))
chat = client.chat.create(
    model="grok-4",
    search_parameters = SearchParameters(
        mode="auto",
        from_date=datetime(2022, 1, 1),
        to_date=datetime(2022, 12, 31)
    )
)
chat.append(user("What is the most viral meme in 2022?"))
response = chat.sample()
print(response.content)
print(response.citations)
Limit the maximum amount of data sources
You can set a limit on how many data sources will be considered in the query via 
"max_search_results"
. The default limit is 20.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        max_search_results=10,
    ),
)
chat.append(user("Can you recommend the top 10 burger places in London?"))
response = chat.sample()
print(response.content)
print(response.citations)
Data sources and parameters
In 
"sources"
 of 
"search_parameters"
, you can add a list of sources to be potentially used in search. Each source is an object with source name and parameters for that source, with the name of the source in the 
"type"
 field.

If nothing is specified, the sources to be used will default to 
"web"
, 
"news"
 and 
"x"
.

For example, the following enables web, X search, news and rss:

JSON


"sources": [
  {"type": "web"},
  {"type": "x"},
  {"type": "news"}
  {"type": "rss"}
]
Overview of data sources and supported parameters
Data Source	Description	Supported Parameters
"web"
Searching on websites.	
"country"
, 
"excluded_websites"
, 
"allowed_websites"
, 
"safe_search"
"x"
Searching X posts.	
"included_x_handles"
, 
"excluded_x_handles"
, 
"post_favorite_count"
, 
"post_view_count"
"news"
Searching from news sources.	
"country"
, 
"excluded_websites"
, 
"safe_search"
"rss"
Retrieving data from the RSS feed provided.	
"links"
Parameter 
"country"
 (Supported by Web and News)
Sometimes you might want to include data from a specific country/region. To do so, you can add an ISO alpha-2 code of the country to 
"country"
 in 
"web"
 or 
"news"
 of the 
"sources"
.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, web_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        sources=[web_source(country="CH")],
    ),
)
chat.append(user("Where is the best place to go skiing this year?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"excluded_websites"
 (Supported by Web and News)
Use 
"excluded_websites"
to exclude websites from the query. You can exclude a maximum of five websites.

This cannot be used with 
"allowed_websites"
 on the same search source.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, news_source, web_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        sources=[
            web_source(excluded_websites=["wikipedia.org"]),
            news_source(excluded_websites=["bbc.co.uk"]),
        ],
    ),
)
chat.append(user("What are some recently discovered alternative DNA shapes"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"allowed_websites"
 (Supported by Web)
Use 
"allowed_websites"
to allow only searching on these websites for the query. You can include a maximum of five websites.

This cannot be used with 
"excluded_websites"
 on the same search source.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, web_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
    mode="auto",
    sources=[web_source(allowed_websites=["x.ai"])],
),
)
chat.append(user("What are the latest releases at xAI?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"included_x_handles"
 (Supported by X)
Use 
"included_x_handles"
 to consider X posts only from a given list of X handles. The maximum number of handles you can include is 10.

This parameter cannot be set together with 
"excluded_x_handles"
.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, x_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        sources=[x_source(included_x_handles=["xai"])],
    ),
)
chat.append(user("What are the latest updates from xAI?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"excluded_x_handles"
 (Supported by X)
Use 
"excluded_x_handles"
 to exclude X posts from a given list of X handles. The maximum number of handles you can exclude is 10.

This parameter cannot be set together with 
"included_x_handles"
.

To prevent the model from citing itself in its responses, the 
"grok"
 handle is automatically excluded by default. If you want to include posts from 
"grok"
 in your search, you must pass it explicitly in the 
"included_x_handles"
 parameter.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, x_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        sources=[x_source(excluded_x_handles=["xai"])],
    ),
)
chat.append(user("What are people saying about xAI?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameters 
"post_favorite_count"
 and 
"post_view_count"
 (Supported by X)
Use 
"post_favorite_count"
 and 
"post_view_count"
 to filter X posts by the number of favorites and views they have. Only posts with at least the specified number of favorites and views will be considered.

You can set both parameters to consider posts with at least the specified number of favorites and views.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, x_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto", # Only consider posts with at least 1000 favorites and 20000 views
        sources=[x_source(post_favorite_count=1000, post_view_count=20000)],
    ),
)
chat.append(user("What are the most popular X posts?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"link"
 (Supported by RSS)
You can also fetch data from a list of RSS feed urls via 
{ "links": ... }
. You can only add one RSS link at the moment.

For example:


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.search import SearchParameters, rss_source
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(
    model="grok-4",
    search_parameters=SearchParameters(
        mode="auto",
        sources=[rss_source(links=["https://status.x.ai/feed.xml"])],
    ),
)
chat.append(user("What are the latest updates on Grok?"))
response = chat.sample()
print(response.content)
print(response.citations)
Parameter 
"safe_search"
 (Supported by Web and News)
Safe search is on by default. You can disable safe search for 
"web"
 and 
"news"
 via 
"sources": [{..., "safe_search": false }]
.
Streaming Response
Streaming outputs is supported by all models with text output capability (Chat, Image Understanding, etc.). It is not supported by models with image output capability (Image Generation).

Streaming outputs uses Server-Sent Events (SSE) that let the server send back the delta of content in event streams.

Streaming responses are beneficial for providing real-time feedback, enhancing user interaction by allowing text to be displayed as it's generated.

To enable streaming, you must set 
"stream": true
 in your request.

When using streaming output with reasoning models, you might want to manually override request timeout to avoid prematurely closing connection.


Python

Javascript
Other

import os
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(
    api_key=os.getenv('XAI_API_KEY'),
    timeout=3600, # Override default timeout with longer timeout for reasoning models
)
chat = client.chat.create(model="grok-4")
chat.append(
    system("You are Grok, a chatbot inspired by the Hitchhikers Guide to the Galaxy."),
)
chat.append(
    user("What is the meaning of life, the universe, and everything?")
)
for response, chunk in chat.stream():
    print(chunk.content, end="", flush=True) # Each chunk's content
    print(response.content, end="", flush=True) # The response object auto-accumulates the chunks
print(response.content) # The full response
You'll get the event streams like these:

Bash


data: {
    "id":"<completion_id>","object":"chat.completion.chunk","created":<creation_time>,
    "model":"grok-4",
    "choices":[{"index":0,"delta":{"content":"Ah","role":"assistant"}}],
    "usage":{"prompt_tokens":41,"completion_tokens":1,"total_tokens":42,
    "prompt_tokens_details":{"text_tokens":41,"audio_tokens":0,"image_tokens":0,"cached_tokens":0}},
    "system_fingerprint":"fp_xxxxxxxxxx"
}
data: {
    "id":"<completion_id>","object":"chat.completion.chunk","created":<creation_time>,
    "model":"grok-4",
    "choices":[{"index":0,"delta":{"content":",","role":"assistant"}}],
    "usage":{"prompt_tokens":41,"completion_tokens":2,"total_tokens":43,
    "prompt_tokens_details":{"text_tokens":41,"audio_tokens":0,"image_tokens":0,"cached_tokens":0}},
    "system_fingerprint":"fp_xxxxxxxxxx"
}
data: [DONE]
It is recommended that you use a client SDK to parse the event stream.

Example streaming responses in Python/Javascript:

Text


Ah, the ultimate question! According to Douglas Adams, the answer is **42**. However, the trick lies in figuring out what the actual question is. If you're looking for a bit more context or a different perspective:
- **Philosophically**: The meaning of life might be to seek purpose, happiness, or to fulfill one's potential.
- **Biologically**: It could be about survival, reproduction, and passing on genes.
- **Existentially**: You create your own meaning through your experiences and choices.
But let's not forget, the journey to find this meaning might just be as important as the answer itself! Keep exploring, questioning, and enjoying the ride through the universe. And remember, don't panic!

Deferred Chat Completions
Deferred Chat Completions are currently available only via REST requests or xAI SDK.

Deferred Chat Completions allow you to create a chat completion, get a 
response_id
, and retrieve the response at a later time. The result would be available to be requested exactly once within 24 hours, after which it would be discarded.

Deferred chat flow
After sending the request to the xAI API, the chat completion result will be available at 
https://api.x.ai/v1/chat/deferred-completion/{request_id}
. The response body will contain 
{'request_id': 'f15c114e-f47d-40ca-8d5c-8c23d656eeb6'}
, and the 
request_id
 value can be inserted into the 
deferred-completion
 endpoint path. Then, we send this GET request to retrieve the deferred completion result.

When the completion result is not ready, the request will return 
202 Accepted
 with an empty response body.

You can access the model's raw thinking trace via the 
message.reasoning_content
 of the chat completion response.

grok-4
 does not return 
reasoning_content
Example
An example code is provided below, where we retry retrieving the result until it have been processed:


Python
Other

import os
from datetime import timedelta
from xai_sdk import Client
from xai_sdk.chat import user, system
client = Client(api_key=os.getenv('XAI_API_KEY'))
chat = client.chat.create(
    model="grok-4",
    messages=[system("You are Zaphod Beeblebrox.")]
)
chat.append(user("126/3=?"))
# Poll the result every 10 seconds for a maximum of 10 minutes
response = chat.defer(
    timeout=timedelta(minutes=10), interval=timedelta(seconds=10)
)
# Print the result when it is ready
print(response.content)
The response body will be the same as what you would expect with non-deferred chat completions:

JSON


{
  "id": "3f4ddfca-b997-3bd4-80d4-8112278a1508",
  "object": "chat.completion",
  "created": 1752077400,
  "model": "grok-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Whoa, hold onto your improbability drives, kid! This is Zaphod Beeblebrox here, the two-headed, three-armed ex-President of the Galaxy, and you're asking me about 126 divided by 3? Pfft, that's kid stuff for a guy who's stolen starships and outwitted the universe itself.\n\nBut get this\u2014126 slashed by 3 equals... **42**! Yeah, that's right, the Ultimate Answer to Life, the Universe, and Everything! Deep Thought didn't compute that for seven and a half million years just for fun, you know. My left head's grinning like a Vogon poet on happy pills, and my right one's already planning a party. If you need more cosmic math or a lift on the Heart of Gold, just holler. Zaphod out! 🚀",
        "refusal": null
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 26,
    "completion_tokens": 168,
    "total_tokens": 498,
    "prompt_tokens_details": {
      "text_tokens": 26,
      "audio_tokens": 0,
      "image_tokens": 0,
      "cached_tokens": 4
    },
    "completion_tokens_details": {
      "reasoning_tokens": 304,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    },
    "num_sources_used": 0
  },
  "system_fingerprint": "fp_44e53da025"
}
For more details, refer to Chat completions and Get deferred chat completions in our REST API Reference.

Asynchronous Requests
When working with the xAI API, you may need to process hundreds or even thousands of requests. Sending these requests sequentially can be extremely time-consuming.

To improve efficiency, you can use 
AsyncClient
 from 
xai_sdk
 or 
AsyncOpenAI
 from 
openai
, which allows you to send multiple requests concurrently. The example below is a Python script demonstrating how to use 
AsyncClient
 to batch and process requests asynchronously, significantly reducing the overall execution time:

The xAI API does not currently offer a batch API.

Rate Limits
Adjust the 
max_concurrent
 param to control the maximum number of parallel requests.

You are unable to concurrently run your requests beyond the rate limits shown in the API console.


Python
Other

import asyncio
from xai_sdk import AsyncClient
from xai_sdk.chat import Response, user
async def main():
    client = AsyncClient(
        api_key=os.getenv("XAI_API_KEY"),
        timeout=3600, # Override default timeout with longer timeout for reasoning models
    )
    model = "grok-4"
    requests = [
        "Tell me a joke",
        "Write a funny haiku",
        "Generate a funny X post",
        "Say something unhinged",
    ]
    # Define a semaphore to limit concurrent requests (e.g., max 2 concurrent requests at a time)
    max_in_flight_requests = 2
    semaphore = asyncio.Semaphore(max_in_flight_requests)
    async def process_request(request) -> Response:
        async with semaphore:
            print(f"Processing request: {request}")
            chat = client.chat.create(model=model, max_tokens=100)
            chat.append(user(request))
            return await chat.sample()
    tasks = []
    for request in requests:
        tasks.append(process_request(request))
    responses = await asyncio.gather(*tasks)
    for i, response in enumerate(responses):
        print(f"Total tokens used for response {i}: {response.usage.total_tokens}")
if **name** == "**main**":
asyncio.run(main())

Function calling
Connect the xAI models to external tools and systems to build AI assistants and various integrations.

With stream response, the function call will be returned in whole in a single chunk, instead of being streamed across chunks.

Introduction
Function calling enables language models to use external tools, which can intimately connect models to digital and physical worlds.

This is a powerful capability that can be used to enable a wide range of use cases.

Calling public APIs for actions ranging from looking up football game results to getting real-time satellite positioning data
Analyzing internal databases
Browsing web pages
Executing code
Interacting with the physical world (e.g. booking a flight ticket, opening your tesla car door, controlling robot arms)
Walkthrough
The request/response flow for function calling can be demonstrated in the following illustration.

Function call request/response flow example
You can think of it as the LLM initiating RPCs (Remote Procedure Calls) to user system. From the LLM's perspective, the "2. Response" is an RPC request from LLM to user system, and the "3. Request" is an RPC response with information that LLM needs.

One simple example of a local computer/server, where the computer/server determines if the response from Grok contains a 
tool_call
, and calls the locally-defined functions to perform user-defined actions:

Local computer/server setup for function calling
The whole process looks like this in pseudocode:

Pseudocode


// ... Define tool calls and their names
messages = []
/* Step 1: Send a new user request */
messages += {<new user request message>}
response = send_request_to_grok(message)
messages += response.choices[0].message  // Append assistant response
while (true) {
    /* Step 2: Run tool call and add tool call result to messages */
    if (response contains tool_call) {
        // Grok asks for tool call
        for (tool in tool_calls) {
            tool_call_result = tool(arguments provided in response) // Perform tool call
            messages += tool_call_result  // Add result to message
        }
    }
    read(user_request)
    if (user_request) {
        messages += {<new user request message>}
    }
    /* Step 3: Send request with tool call result to Grok*/
    response = send_request_to_grok(message)
    print(response)
}
We will demonstrate the function calling in the following Python script. First, let's create an API client:


Python
Other

import os
import json
from xai_sdk import Client
from xai_sdk.chat import tool, tool_result, user
client = Client(api_key=os.getenv('XAI_API_KEY'))
chat = client.chat.create(model="grok-4")
Preparation - Define tool functions and function mapping
Define tool functions as callback functions to be called when model requests them in response.

Normally, these functions would either retrieve data from a database, or call another API endpoint, or perform some actions. For demonstration purposes, we hardcode to return 59° Fahrenheit/15° Celsius as the temperature, and 15,000 feet as the cloud ceiling.

The parameters definition will be sent in the initial request to Grok, so Grok knows what tools and parameters are available to be called.

To reduce human error, you can define the tools partially using Pydantic.

Function definition using Pydantic:


Python
Other

from typing import Literal
from pydantic import BaseModel, Field
class TemperatureRequest(BaseModel):
    location: str = Field(description="The city and state, e.g. San Francisco, CA")
    unit: Literal["celsius", "fahrenheit"] = Field(
        "fahrenheit", description="Temperature unit"
    )
class CeilingRequest(BaseModel):
    location: str = Field(description="The city and state, e.g. San Francisco, CA")
def get_current_temperature(request: TemperatureRequest):
    temperature = 59 if request.unit.lower() == "fahrenheit" else 15
    return {
        "location": request.location,
        "temperature": temperature,
        "unit": request.unit,
    }
def get_current_ceiling(request: CeilingRequest):
    return {
        "location": request.location,
        "ceiling": 15000,
        "ceiling_type": "broken",
        "unit": "ft",
    }
# Generate the JSON schema from the Pydantic models
get_current_temperature_schema = TemperatureRequest.model_json_schema()
get_current_ceiling_schema = CeilingRequest.model_json_schema()
# Definition of parameters with Pydantic JSON schema
tool_definitions = [
    tool(
        name="get_current_temperature",
        description="Get the current temperature in a given location",
        parameters=get_current_temperature_schema,
    ),
    tool(
        name="get_current_ceiling",
        description="Get the current cloud ceiling in a given location",
        parameters=get_current_ceiling_schema,
    ),
]
Function definition using raw dictionary:


Python
Other

from typing import Literal
def get_current_temperature(location: str, unit: Literal["celsius", "fahrenheit"] = "fahrenheit"):
    temperature = 59 if unit == "fahrenheit" else 15
    return {
        "location": location,
        "temperature": temperature,
        "unit": unit,
    }
def get_current_ceiling(location: str):
    return {
        "location": location,
        "ceiling": 15000,
        "ceiling_type": "broken",
        "unit": "ft",
    }
# Raw dictionary definition of parameters
tool_definitions = [
    tool(
        name="get_current_temperature",
        description="Get the current temperature in a given location",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "fahrenheit",
                },
            },
            "required": ["location"],
        },
    ),
    tool(
        name="get_current_ceiling",
        description="Get the current cloud ceiling in a given location",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                }
            },
            "required": ["location"],
        },
    ),
]
Create a string -> function mapping, so we can call the function when model sends it's name. e.g.

Python


tools_map = {
    "get_current_temperature": get_current_temperature,
    "get_current_ceiling": get_current_ceiling,
}
1. Send initial message
With all the functions defined, it's time to send our API request to Grok!

Now before we send it over, let's look at how the generic request body for a new task looks like.

Here we assume a previous tool call has Note how the tool call is referenced three times:

By 
id
 and 
name
 in "Mesage History" assistant's first response
By 
tool_call_id
 in "Message History" tool's content
In the 
tools
 field of the request body
Function call new request body
Now we compose the request messages in the request body and send it over to Grok. Grok should return a response that asks us for a tool call.


Python
Other

chat = client.chat.create(
    model="grok-4",
    tools=tool_definitions,
    tool_choice="auto",
)
chat.append(user("What's the temperature like in San Francisco?"))
response = chat.sample()
# You can inspect the response tool calls which contains a tool call
print(response.tool_calls)
2. Run tool functions if Grok asks tool call and append function returns to message
We retrieve the tool function names and arguments that Grok wants to call, run the functions, and add the result to messages.

At this point, you can choose to only respond to tool call with results or add a new user message request.

The 
tool
 message would contain the following:

JSON


{
    "role": "tool",
    "content": <json string of tool function's returned object>,
    "tool_call_id": <tool_call.id included in the tool call response by Grok>,
}
The request body that we try to assemble and send back to Grok. Note it looks slightly different from the new task request body:

Request body after processing tool call
The corresponding code to append messages:


Python
Other

# Append assistant message including tool calls to messages
chat.append(response)
# Check if there is any tool calls in response body
# You can also wrap this in a function to make the code cleaner
if response.tool_calls:
    for tool_call in response.tool_calls:
        # Get the tool function name and arguments Grok wants to call
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        # Call one of the tool function defined earlier with arguments
        result = tools_map[function_name](**function_args)
        # Append the result from tool function call to the chat message history
        chat.append(tool_result(result))
        
3. Send the tool function returns back to the model to get the response

Python
Other

response = chat.sample()
print(response.content)
4. (Optional) Continue the conversation
You can continue the conversation following Step 2. Otherwise you can terminate.

Function calling modes
By default, the model will automatically decide whether a function call is necessary and select which functions to call, as determined by the 
tool_choice: "auto"
 setting.

We offer three ways to customize the default behavior:

To force the model to always call one or more functions, you can set 
tool_choice: "required"
. The model will then always call function. Note this could force the model to hallucinate parameters.
To force the model to call a specific function, you can set 
tool_choice: {"type": "function", "function": {"name": "my_function"}}
.
To disable function calling and force the model to only generate a user-facing message, you can either provide no tools, or set 
tool_choice: "none"
.
Parallel function calling
By default, parallel function calling is enabled, so you can process multiple function calls in one request/response cycle. When two or more tool calls are required, all of the tool call requests will be included in the response body. You can disable it by setting 
parallel_function_calling : "false"
.

Complete Example with Vercel AI SDK
The Vercel AI SDK simplifies function calling by handling tool definition, mapping, and execution automatically. Here's a complete example:

Javascript


import { xai } from '@ai-sdk/xai';
import { streamText, tool, stepCountIs } from 'ai';
import { z } from 'zod';
const result = streamText({
  model: xai('grok-4'),
  tools: {
    getCurrentTemperature: tool({
      description: 'Get the current temperature in a given location',
      inputSchema: z.object({
        location: z
          .string()
          .describe('The city and state, e.g. San Francisco, CA'),
        unit: z
          .enum(['celsius', 'fahrenheit'])
          .default('fahrenheit')
          .describe('Temperature unit'),
      }),
      execute: async ({ location, unit }) => {
        const temperature = unit === 'fahrenheit' ? 59 : 15;
        return {
          location,
          temperature,
          unit,
        };
      },
    }),
    getCurrentCeiling: tool({
      description: 'Get the current cloud ceiling in a given location',
      inputSchema: z.object({
        location: z
          .string()
          .describe('The city and state, e.g. San Francisco, CA'),
      }),
      execute: async ({ location }) => {
        return {
          location,
          ceiling: 15000,
          ceiling_type: 'broken',
          unit: 'ft',
        };
      },
    }),
  },
  stopWhen: stepCountIs(5),
  prompt: "What's the temperature like in San Francisco?",
});
for await (const chunk of result.fullStream) {
  switch (chunk.type) {
    case 'text-delta':
      process.stdout.write(chunk.text);
      break;
    case 'tool-call':
      console.log(`Tool call: ${chunk.toolName}`, chunk.input);
      break;
    case 'tool-result':
      console.log(`Tool response: ${chunk.toolName}`, chunk.output);
      break;
  }
}
With the Vercel AI SDK, you don't need to manually:

Map tool names to functions
Parse tool call arguments
Append tool results back to messages
Handle the request/response cycle
The SDK automatically handles all of these steps, making function calling much simpler.

Structured Outputs
Structured Outputs is a feature that lets the API return responses in a specific, organized format, like JSON or other schemas you define. Instead of getting free-form text, you receive data that's consistent and easy to parse.

Ideal for tasks like document parsing, entity extraction, or report generation, it lets you define schemas using tools like Pydantic or Zod to enforce data types, constraints, and structure.

When using structured outputs, the LLM's response is guaranteed to match your input schema.

Supported models
Structured outputs is supported by all language models later than 
grok-2-1212
 and 
grok-2-vision-1212
.

Supported schemas
For structured output, the following types are supported for structured output:

string
minLength
 and 
maxLength
 properties are not supported
number
integer
float
object
array
minItems
 and 
maxItem
 properties are not supported
maxContains
 and 
minContains
 properties are not supported
boolean
enum
anyOf
allOf
 is not supported at the moment.

Example: Invoice Parsing
A common use case for Structured Outputs is parsing raw documents. For example, invoices contain structured data like vendor details, amounts, and dates, but extracting this data from raw text can be error-prone. Structured Outputs ensure the extracted data matches a predefined schema.

Let's say you want to extract the following data from an invoice:

Vendor name and address
Invoice number and date
Line items (description, quantity, price)
Total amount and currency
We'll use structured outputs to have Grok generate a strongly-typed JSON for this.

Step 1: Defining the Schema
You can use Pydantic or Zod to define your schema.

Python

from datetime import date
from enum import Enum
from typing import List
from pydantic import BaseModel, Field
class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
class LineItem(BaseModel):
    description: str = Field(description="Description of the item or service")
    quantity: int = Field(description="Number of units", ge=1)
    unit_price: float = Field(description="Price per unit", ge=0)
class Address(BaseModel):
    street: str = Field(description="Street address")
    city: str = Field(description="City")
    postal_code: str = Field(description="Postal/ZIP code")
    country: str = Field(description="Country")
class Invoice(BaseModel):
    vendor_name: str = Field(description="Name of the vendor")
    vendor_address: Address = Field(description="Vendor's address")
    invoice_number: str = Field(description="Unique invoice identifier")
    invoice_date: date = Field(description="Date the invoice was issued")
    line_items: List[LineItem] = Field(description="List of purchased items/services")
    total_amount: float = Field(description="Total amount due", ge=0)
    currency: Currency = Field(description="Currency of the invoice")
Step 2: Prepare The Prompts
System Prompt
The system prompt instructs the model to extract invoice data from text. Since the schema is defined separately, the prompt can focus on the task without explicitly specifying the required fields in the output JSON.

Text


Given a raw invoice, carefully analyze the text and extract the relevant invoice data into JSON format.
Example Invoice Text
Text


Vendor: Acme Corp, 123 Main St, Springfield, IL 62704
Invoice Number: INV-2025-001
Date: 2025-02-10
Items:
- Widget A, 5 units, $10.00 each
- Widget B, 2 units, $15.00 each
Total: $80.00 USD
Step 3: The Final Code
Use the structured outputs feature of the the SDK to parse the invoice.


Python

Javascript
Other

import os
from datetime import date
from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from xai_sdk import Client
from xai_sdk.chat import system, user
# Pydantic Schemas
class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
class LineItem(BaseModel):
    description: str = Field(description="Description of the item or service")
    quantity: int = Field(description="Number of units", ge=1)
    unit_price: float = Field(description="Price per unit", ge=0)
class Address(BaseModel):
    street: str = Field(description="Street address")
    city: str = Field(description="City")
    postal_code: str = Field(description="Postal/ZIP code")
    country: str = Field(description="Country")
class Invoice(BaseModel):
    vendor_name: str = Field(description="Name of the vendor")
    vendor_address: Address = Field(description="Vendor's address")
    invoice_number: str = Field(description="Unique invoice identifier")
    invoice_date: date = Field(description="Date the invoice was issued")
    line_items: List[LineItem] = Field(description="List of purchased items/services")
    total_amount: float = Field(description="Total amount due", ge=0)
    currency: Currency = Field(description="Currency of the invoice")
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(model="grok-4")
chat.append(system("Given a raw invoice, carefully analyze the text and extract the invoice data into JSON format."))
chat.append(
user("""
Vendor: Acme Corp, 123 Main St, Springfield, IL 62704
Invoice Number: INV-2025-001
Date: 2025-02-10
Items: - Widget A, 5 units, $10.00 each - Widget B, 2 units, $15.00 each
Total: $80.00 USD
""")
)
# The parse method returns a tuple of the full response object as well as the parsed pydantic object.
response, invoice = chat.parse(Invoice)
assert isinstance(invoice, Invoice)
# Can access fields of the parsed invoice object directly
print(invoice.vendor_name)
print(invoice.invoice_number)
print(invoice.invoice_date)
print(invoice.line_items)
print(invoice.total_amount)
print(invoice.currency)
# Can also access fields from the raw response object such as the content.
# In this case, the content is the JSON schema representation of the parsed invoice object
print(response.content)
Step 4: Type-safe Output
The output will always be type-safe and respect the input schema.

JSON


{
  "vendor_name": "Acme Corp",
  "vendor_address": {
    "street": "123 Main St",
    "city": "Springfield",
    "postal_code": "62704",
    "country": "IL"
  },
  "invoice_number": "INV-2025-001",
  "invoice_date": "2025-02-10",
  "line_items": [
    { "description": "Widget A", "quantity": 5, "unit_price": 10.0 },
    { "description": "Widget B", "quantity": 2, "unit_price": 15.0 }
  ],
  "total_amount": 80.0,
  "currency": "USD"
}
Fingerprint
For each request to the xAI API, the response body will include a unique 
system_fingerprint
 value. This fingerprint serves as an identifier for the current state of the backend system's configuration.

Example:

Bash


curl https://api.x.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -d '{
        "messages": [
          {
            "role": "system",
            "content": "You are Grok, a chatbot inspired by the Hitchhikers Guide to the Galaxy."
          },
          {
            "role": "user",
            "content": "What is the meaning of life, the universe, and everything?"
          }
        ],
        "model": "grok-4",
        "stream": false,
        "temperature": 0
      }'
Response:

JSON


{..., "system_fingerprint":"fp_6ca29cf396"}
You can automate your system to keep track of the 
system_fingerprint
 along with token consumption and other metrics.

Usage of fingerprint
Monitoring System Changes: The system fingerprint acts as a version control for the backend configuration. If any part of the backend system—such as model parameters, server settings, or even the underlying infrastructure—changes, the fingerprint will also change. This allows developers to track when and how the system has evolved over time. This is crucial for debugging, performance optimization, and ensuring consistency in API responses.
Security and Integrity: The fingerprint can be used to ensure the integrity of the response. If a response's fingerprint matches the expected one based on a recent system configuration, it helps in verifying that the data hasn't been tampered with during transmission or that the service hasn't been compromised. The fingerprint will change over time and it is expected.
Compliance and Auditing: For regulated environments, this fingerprint can serve as part of an audit trail, showing when specific configurations were in use for compliance purposes.