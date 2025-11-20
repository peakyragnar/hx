 Here is a comprehensive explanation of how the product runs in production, including all the external
  services it relies on.

  Production Architecture Overview

  The production environment is a modern, cloud-native setup that leverages several best-in-class services to
  provide a scalable, secure, and reliable application. The architecture is broken down into a frontend, a
  backend, a database, and several third-party services for specific functionalities.

  Here is a detailed breakdown of each component:

 1. Frontend Hosting: Render Static Site

   * What it is: Render can host static sites (HTML/CSS/JS) on its CDN with custom domains.
   * How it's used: The frontend in the `ui/` directory is deployed as a Render Static Site with `heretix.ai`/`www.heretix.ai` pointing at `heretix-ui.onrender.com`.
   * Why it's used: Using Render for the frontend keeps hosting in one platform, provides fast global delivery, and simplifies deploys alongside the API.

  2. Backend API Hosting: Render

   * What it is: Render is a cloud platform for hosting web applications, databases, and other services.
   * How it's used: The backend API, which is a FastAPI application, is packaged into a Docker container and
     deployed as a "Web Service" on Render. The Dockerfile in the repository defines how the container is built.
   * Why it's used: Render provides a simple and scalable way to deploy Dockerized applications. It handles the
     complexities of managing servers, so the developers can focus on writing code.

  3. Database: Neon

   * What it is: Neon is a serverless, managed PostgreSQL database provider.
   * How it's used: The production database, which stores all the application data such as user accounts,
     subscriptions, and the results of the RPL/WEL checks, is a PostgreSQL database hosted on Neon.
   * Why it's used: Neon provides a fully managed database service, which means that the developers don't have
     to worry about database administration tasks like backups, scaling, and security.

  4. AI Model: OpenAI

   * What it is: OpenAI provides large language models (LLMs) via an API.
   * How it's used: The application uses GPT-5 from OpenAI as the core AI model for both the Raw Prior Lens
     (RPL) and the Web-Informed Lens (WEL). The OPENAI_API_KEY is used to authenticate with the OpenAI API.
   * Why it's used: GPT-5 is a powerful AI model that is capable of the nuanced reasoning required for the RPL
     and WEL analyses.

  5. Web Search for WEL: Tavily

   * What it is: Tavily is a search API designed for AI applications.
   * How it's used: When the Web-Informed Lens (WEL) needs to fetch evidence from the web, it uses the Tavily 
     API to perform the search. The TAVILY_API_KEY is used to authenticate with the Tavily API.
   * Why it's used: Tavily provides a search API that is optimized for AI agents, which makes it a good choice
     for the WEL feature.

  6. Email Delivery: Postmark

   * What it is: Postmark is a service for sending transactional emails.
   * How it's used: The application uses Postmark to send magic link emails to users when they want to sign in.
     The POSTMARK_TOKEN is used to authenticate with the Postmark API.
   * Why it's used: Using a dedicated email sending service like Postmark ensures that the emails are delivered
     reliably and are not marked as spam.

  7. Payments and Subscriptions: Stripe

   * What it is: Stripe is a platform for handling online payments and subscriptions.
   * How it's used: The application uses Stripe to manage user subscriptions. This includes creating checkout
     sessions, handling webhooks to update subscription statuses, and managing customer billing information. The
     various STRIPE_* keys in the configuration are used to integrate with the Stripe API.
   * Why it's used: Stripe is a very popular and developer-friendly platform for handling payments, and it
     provides a secure and reliable way to manage subscriptions.

  8. Prediction Market Data: Kalshi

   * What it is: Kalshi is a regulated prediction market platform where users can trade on the outcome of future events.
   * How it's used: The application is configured with a KALSHI_API_KEY, which suggests that it integrates withthe Kalshi API. While the exact usage is not detailed in the documents I've reviewed, it is likely used to fetch data from Kalshi's prediction markets related to the claims being analyzed. This could be used to see if there is an active market for a particular claim and what the market consensus is.
