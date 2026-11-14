/**
 * Generated from openapi.json by `pnpm gen:api-types` (scripts/api-types.ts). Do not edit.
 * openapi.json comes from `uv run python -m app.interfaces.web_contract` in api/.
 */

export interface paths {
    "/api/v1/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search Products */
        get: operations["search_products_api_v1_products_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/customer-context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Customer Context */
        get: operations["get_customer_context_api_v1_customer_context_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/recipes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search Recipes */
        get: operations["search_recipes_api_v1_recipes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/recipes/{recipe_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Recipe */
        get: operations["get_recipe_api_v1_recipes__recipe_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Build Quote */
        post: operations["build_quote_api_v1_quotes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Current Quote
         * @description The caller's newest quote, for the webshop chat panel (§9.6). Not an agent tool.
         */
        get: operations["current_quote_api_v1_quotes_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes/{quote_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Quote
         * @description One of the caller's company's quotes, for the webshop chat panel (§9.6).
         */
        get: operations["get_quote_api_v1_quotes__quote_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes/{quote_id}/update": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Update Quote
         * @description The body is the full new line list, as in `build_quote`. Returns a new quote.
         */
        post: operations["update_quote_api_v1_quotes__quote_id__update_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes/{quote_id}/confirmation-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Confirmation */
        post: operations["request_confirmation_api_v1_quotes__quote_id__confirmation_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quotes/{quote_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Order Status */
        get: operations["get_order_status_api_v1_quotes__quote_id__status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Orders
         * @description Totals since `EVENT_START`, then at most 200 cards that match the filters, grouped by
         *     company, newest activity first.
         */
        get: operations["get_orders_api_v1_public_orders_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/orders/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Order */
        get: operations["get_order_api_v1_public_orders__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/orders/{session_id}/steps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Steps */
        get: operations["get_steps_api_v1_public_orders__session_id__steps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/orders/{session_id}/transcript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Transcript */
        get: operations["get_transcript_api_v1_public_orders__session_id__transcript_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/orders/{session_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Events
         * @description The session's full events; `?download=1` sends them as a file.
         */
        get: operations["get_events_api_v1_public_orders__session_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/audit/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Verify
         * @description #41's chain check: one session's events, or the whole chain without `session_id`.
         */
        get: operations["get_verify_api_v1_public_audit_verify_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Stream
         * @description Server-sent events: `snapshot` (as `GET /orders`, with the same filters), then
         *     `order_updated` (filtered), `step` and `transcript`, each with `id` = the
         *     `status_events` id. A reconnect with `Last-Event-ID` gets the missed events first.
         */
        get: operations["stream_api_v1_public_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/demo/accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Demo Account
         * @description Log this browser in as a user of the number's company, creating it if it's new.
         *
         *     The same browser typing the same number again stays the same user.
         */
        post: operations["create_demo_account_api_v1_demo_accounts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Me
         * @description This browser's session, or the dev caller when DEV_FAKE_CALLER is on, else 401.
         *
         *     A bearer token doesn't count here: REST reads only the cookie.
         */
        get: operations["get_me_api_v1_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Log In
         * @description Log in with email and password. 401 for a wrong email or password alike; 429 after
         *     10 failed tries for the email within 10 minutes.
         *
         *     `phone_required` tells the login page to ask a hand-out account for its number.
         */
        post: operations["log_in_api_v1_session_post"];
        /**
         * Delete Session
         * @description Log out: revoke this browser's session and clear the cookie. Safe to repeat.
         */
        delete: operations["delete_session_api_v1_session_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/signup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Signup
         * @description Open sign-up for the connectors: email, password (10 characters or more) and number.
         *
         *     Logs the browser in. The number's company is found or created as for a demo account.
         */
        post: operations["signup_api_v1_signup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/phone": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Set Phone
         * @description Set the number of a hand-out account on its first login. Only while it has none: 409
         *     after that.
         */
        post: operations["set_phone_api_v1_me_phone_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/private/inbox": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Inbox
         * @description This browser's messages, oldest first. Held messages appear when the call ends.
         */
        get: operations["get_inbox_api_v1_private_inbox_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/private/inbox/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Inbox Stream
         * @description Server-sent events: `snapshot` (the inbox so far, as `GET /inbox`), then one
         *     `inbox_message` per new message, with the message as JSON.
         */
        get: operations["inbox_stream_api_v1_private_inbox_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/oauth/requests/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Request
         * @description What the consent page shows. 404 when the request is unknown or expired.
         */
        get: operations["get_request_api_v1_oauth_requests__request_id__get"];
        put?: never;
        /**
         * Decide
         * @description Allow issues a code for this user; Cancel sends `access_denied`. Either way the
         *     browser goes to `redirect_to`, back to the client.
         */
        post: operations["decide_api_v1_oauth_requests__request_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/confirmations/{token}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Confirmation
         * @description The page's view. Never uses the token up; stays readable as the receipt.
         */
        get: operations["get_confirmation_api_v1_confirmations__token__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/confirmations/{token}/acknowledgements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Acknowledge */
        post: operations["acknowledge_api_v1_confirmations__token__acknowledgements_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/confirmations/{token}/edits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Edit */
        post: operations["edit_api_v1_confirmations__token__edits_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/confirmations/{token}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm */
        post: operations["confirm_api_v1_confirmations__token__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/confirmations/{token}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_api_v1_confirmations__token__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AcknowledgeRequest
         * @description `option_id` is the buyer's pick for a `choose` flag. An option that changes the
         *     order makes a new quote, with the flag acknowledged on it.
         */
        AcknowledgeRequest: {
            /** Quote Hash */
            quote_hash: string;
            /** Flag Key */
            flag_key: string;
            /** Option Id */
            option_id?: string | null;
        };
        /** AcknowledgedFlag */
        AcknowledgedFlag: {
            /** Flag Key */
            flag_key: string;
            /** Code */
            code: string;
            /**
             * At
             * Format: date-time
             */
            at: string;
        };
        /**
         * AgentInfo
         * @description Assumed: the agent and prompt version that ran the session.
         */
        AgentInfo: {
            name: components["schemas"]["Localized"];
            /** Prompt Version */
            prompt_version: string | null;
        };
        /** Alternative */
        Alternative: {
            /** Product Id */
            product_id: string;
            label: components["schemas"]["Localized"];
            /** Quantity Sales Units */
            quantity_sales_units: number;
            /** Line Total Cents */
            line_total_cents: number;
        };
        /**
         * AskedLine
         * @description Echo of what the buyer asked for.
         */
        AskedLine: {
            /** Text */
            text: string | null;
            /** Quantity */
            quantity: number;
            unit: components["schemas"]["RequestedUnit"];
            /** Package Word */
            package_word: string | null;
            /**
             * Needed By
             * Format: date
             */
            needed_by: string;
        };
        /**
         * AuditEvent
         * @description A full redacted event, as `/events` returns it. The payload shape depends on `type`.
         *
         *     `payload_hash` covers `{payload, text_fi, text_en}` exactly as stored (docs/audit-chain.md),
         *     so the raw sentences are here too, null when the event has none; `text` turns a null into
         *     an empty string for display. `payload` is null when it was deleted after the event.
         */
        AuditEvent: {
            /** Seq */
            seq: number;
            /** Order Index */
            order_index: number;
            /** Session Id */
            session_id: string;
            /** Quote Id */
            quote_id: string | null;
            /** At */
            at: string;
            /** Actor */
            actor: string;
            /** Type */
            type: string;
            text: components["schemas"]["Localized"];
            /** Payload Hash */
            payload_hash: string;
            /** Prev Hash */
            prev_hash: string;
            /** Session Prev Hash */
            session_prev_hash: string | null;
            /** Hash */
            hash: string;
            channel: components["schemas"]["Channel"];
            /** Identity Masked */
            identity_masked: string | null;
            /** Payload */
            payload: {
                [key: string]: unknown;
            } | null;
            /** Text Fi */
            text_fi?: string | null;
            /** Text En */
            text_en?: string | null;
        };
        /** BuildQuoteRequest */
        BuildQuoteRequest: {
            /** Lines */
            lines: components["schemas"]["LineRequest"][];
        };
        /** CancelRequest */
        CancelRequest: {
            /** Quote Hash */
            quote_hash: string;
        };
        /**
         * CardFlag
         * @description A flag on a card, for "2 flags: stock not confirmed, new product".
         */
        CardFlag: {
            /** Code */
            code: string;
            short: components["schemas"]["Localized"];
        };
        /**
         * Channel
         * @description The channel a session came in through, one tile each on the overview.
         * @enum {string}
         */
        Channel: "phone" | "web_chat" | "webmcp" | "mcp";
        /** ChooseAlternativeEdit */
        ChooseAlternativeEdit: {
            /** Quote Hash */
            quote_hash: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            op: "choose_alternative";
            /** Line Id */
            line_id: string;
            /** Alternative Id */
            alternative_id: string;
        };
        /**
         * Claim
         * @description Product claims, as the product data states them.
         *
         *     `lactose_free` means a lactose-free product only; a low-lactose product does not count.
         * @enum {string}
         */
        Claim: "lactose_free" | "gluten_free" | "vegan" | "vegetarian";
        /**
         * Clarification
         * @description The single question back to the buyer. `options` may be empty for an open question.
         */
        Clarification: {
            /** Line Id */
            line_id: string;
            question: components["schemas"]["Localized"];
            /** Options */
            options: components["schemas"]["Alternative"][];
        };
        /** CompanyGroup */
        CompanyGroup: {
            /** Name */
            name: string;
            /** Exclusions */
            exclusions: components["schemas"]["Exclusion"][];
            /** Orders */
            orders: components["schemas"]["OrderCard"][];
        };
        /** CompanyRef */
        CompanyRef: {
            /** Name */
            name: string;
            /** Exclusions */
            exclusions: components["schemas"]["Exclusion"][];
        };
        /** ConfirmRequest */
        ConfirmRequest: {
            /** Quote Hash */
            quote_hash: string;
        };
        /** ConfirmResponse */
        ConfirmResponse: {
            /** Order Number */
            order_number: string;
            /**
             * Confirmed At
             * Format: date-time
             */
            confirmed_at: string;
        };
        /** ConfirmationCompany */
        ConfirmationCompany: {
            /** Name */
            name: string;
        };
        /**
         * ConfirmationErrorDetail
         * @description The `detail` of a refused action: `{"detail": {"text": {...}, "line_id": ...}}`.
         */
        ConfirmationErrorDetail: {
            text: components["schemas"]["Localized"];
            /** Line Id */
            line_id?: string | null;
        };
        /** ConfirmationQuote */
        ConfirmationQuote: {
            /** Quote Id */
            quote_id: string;
            /** Version */
            version: number;
            /** Quote Hash */
            quote_hash: string;
            /** Total Cents */
            total_cents: number;
            delivery: components["schemas"]["DeliverySummary"] | null;
        };
        /** ConfirmationRequestResponse */
        ConfirmationRequestResponse: {
            /** Sent To Masked */
            sent_to_masked: string;
            /**
             * Delivery Status
             * @enum {string}
             */
            delivery_status: "held" | "sent" | "failed" | "off";
            /** Inbox */
            inbox: boolean;
        };
        /** ConfirmationSession */
        ConfirmationSession: {
            channel: components["schemas"]["Channel"];
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
        };
        /** ConfirmationView */
        ConfirmationView: {
            /**
             * State
             * @enum {string}
             */
            state: "ready" | "requote_needed" | "confirmed" | "cancelled" | "expired" | "invalid";
            /**
             * Lang
             * @enum {string}
             */
            lang: "fi" | "en";
            /** Expires At */
            expires_at: string | null;
            company: components["schemas"]["ConfirmationCompany"];
            session: components["schemas"]["ConfirmationSession"];
            /** Exclusions */
            exclusions: components["schemas"]["ExclusionLabel"][];
            quote: components["schemas"]["ConfirmationQuote"];
            /** Lines */
            lines: components["schemas"]["QuoteLine"][];
            /** Groups */
            groups: components["schemas"]["GroupSubtotal"][];
            /** Not Ordered */
            not_ordered: components["schemas"]["NotOrdered"][];
            /** Flags */
            flags: components["schemas"]["ViewFlag"][];
            change: components["schemas"]["QuoteChange"] | null;
            order: components["schemas"]["ConfirmedOrder"] | null;
        };
        /** ConfirmedOrder */
        ConfirmedOrder: {
            /** Order Number */
            order_number: string;
            /**
             * Confirmed At
             * Format: date-time
             */
            confirmed_at: string;
            /** Acknowledged */
            acknowledged: components["schemas"]["AcknowledgedFlag"][];
        };
        /**
         * ConnectDecision
         * @description `POST /api/v1/oauth/requests/{id}`: Allow (true) or Cancel (false).
         */
        ConnectDecision: {
            /** Allow */
            allow: boolean;
        };
        /**
         * ConnectRedirect
         * @description Where the browser goes next: the client's redirect URI with a code or an error.
         */
        ConnectRedirect: {
            /** Redirect To */
            redirect_to: string;
        };
        /**
         * ConnectRequestView
         * @description `GET /api/v1/oauth/requests/{id}`: what the consent page shows.
         *
         *     "Allow <client_name> to order for <company_name>?" `redirect_host` is where the browser
         *     goes next (the MCP spec asks the consent screen to show it).
         */
        ConnectRequestView: {
            /** Client Name */
            client_name: string;
            /** Company Name */
            company_name: string;
            /** Phone Masked */
            phone_masked: string;
            /** Redirect Host */
            redirect_host: string;
        };
        /** CustomerContext */
        CustomerContext: {
            /** Company Name */
            company_name: string;
            /** Phone Masked */
            phone_masked: string;
            /** Exclusions */
            exclusions: components["schemas"]["ExclusionLabel"][];
            /** Usual Items */
            usual_items: components["schemas"]["UsualItem"][];
            /**
             * Lang
             * @enum {string}
             */
            lang: "fi" | "en";
        };
        /**
         * Decision
         * @enum {string}
         */
        Decision: "ready" | "needs_clarification" | "rejected";
        /** DeliverySummary */
        DeliverySummary: {
            /**
             * Earliest
             * Format: date
             */
            earliest: string;
            /**
             * Latest
             * Format: date
             */
            latest: string;
        };
        /**
         * DemoAccountRequest
         * @description `POST /api/v1/demo/accounts`: typing a phone number is the login.
         *
         *     `phone_e164` may be typed loosely ("040 123 4512"); the server normalises it, reading a
         *     number without a country code as Finnish.
         */
        DemoAccountRequest: {
            /** Phone E164 */
            phone_e164: string;
            /** Exclusions */
            exclusions: components["schemas"]["Exclusion"][];
            /**
             * Lang
             * @enum {string}
             */
            lang: "fi" | "en";
        };
        /**
         * DemoAccountResponse
         * @description The browser's demo user. The session token travels only in the `simo_session` cookie.
         */
        DemoAccountResponse: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Company Name */
            company_name: string;
            /** Phone Masked */
            phone_masked: string;
            /** Exclusions */
            exclusions: components["schemas"]["Exclusion"][];
            /** Usual Items */
            usual_items: components["schemas"]["UsualItem"][];
            /** New Company */
            new_company: boolean;
            /** New User */
            new_user: boolean;
        };
        /**
         * Exclusion
         * @description Kitchen exclusions: the allergens and diets the kitchen rules out.
         * @enum {string}
         */
        Exclusion: "milk_free" | "lactose_free" | "gluten_free" | "nut_free" | "egg_free" | "fish_free" | "vegan";
        /** ExclusionLabel */
        ExclusionLabel: {
            key: components["schemas"]["Exclusion"];
            label: components["schemas"]["Localized"];
        };
        /**
         * Flag
         * @description A notice on the quote. The buyer acknowledges it on the confirmation page.
         */
        Flag: {
            /** Flag Key */
            flag_key: string;
            /** Code */
            code: string;
            /** Line Ids */
            line_ids: string[];
            /**
             * Kind
             * @enum {string}
             */
            kind: "acknowledge" | "choose";
            text: components["schemas"]["Localized"];
            /**
             * Options
             * @default []
             */
            options: components["schemas"]["FlagOption"][];
        };
        /** FlagOption */
        FlagOption: {
            /** Option Id */
            option_id: string;
            label: components["schemas"]["Localized"];
            /** Line Total Cents */
            line_total_cents: number;
        };
        /** GroupSubtotal */
        GroupSubtotal: {
            /** Group */
            group: string;
            /** Line Ids */
            line_ids: string[];
            /** Subtotal Cents */
            subtotal_cents: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * InboxMessage
         * @description One message in the simulated phone (`InboxMessage` in `web/src/lib/demo/types.ts`).
         */
        InboxMessage: {
            /** Id */
            id: string;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Text */
            text: string;
            /** Link */
            link: string;
        };
        /**
         * LineRequest
         * @description One structured line from the agent. The engine never sees raw speech.
         */
        LineRequest: {
            /** Line Id */
            line_id: string;
            /** Product Id */
            product_id?: string | null;
            /**
             * Usual
             * @default false
             */
            usual: boolean;
            /** Text */
            text?: string | null;
            /**
             * Claims
             * @default []
             */
            claims: components["schemas"]["Claim"][];
            /** Category */
            category?: string | null;
            /** Quantity */
            quantity: number | string;
            unit: components["schemas"]["RequestedUnit"];
            /** Package Word */
            package_word?: string | null;
            /**
             * Needed By
             * Format: date
             */
            needed_by: string;
            recipe_ref?: components["schemas"]["RecipeRef"] | null;
            /** Group */
            group?: string | null;
        };
        /**
         * Localized
         * @description The same text in Finnish and English.
         */
        Localized: {
            /** Fi */
            fi: string;
            /** En */
            en: string;
        };
        /**
         * LoginRequest
         * @description `POST /api/v1/session`: email and password log the browser in.
         */
        LoginRequest: {
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /**
         * LoginResponse
         * @description The session travels in the `simo_session` cookie.
         *
         *     `phone_required` is true for a hand-out account that has no number yet: the login
         *     page then asks for it (`POST /api/v1/me/phone`) before going on.
         */
        LoginResponse: {
            /** Phone Required */
            phone_required: boolean;
        };
        /**
         * Me
         * @description `GET /api/v1/me`: the signed-in user's company and kitchen profile.
         */
        Me: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Company Name */
            company_name: string;
            /** Phone Masked */
            phone_masked: string;
            /** Exclusions */
            exclusions: components["schemas"]["Exclusion"][];
            /**
             * Lang
             * @enum {string}
             */
            lang: "fi" | "en";
        };
        /**
         * NotOrdered
         * @description A recipe ingredient without a product link. The recipe data is Finnish only.
         */
        NotOrdered: {
            /** Name */
            name: string;
            /** Quantity */
            quantity: number | null;
            /** Unit */
            unit: string | null;
            reason: components["schemas"]["Localized"];
        };
        /** OrderCard */
        OrderCard: {
            /** Session Id */
            session_id: string;
            /** Order Number */
            order_number: string | null;
            channel: components["schemas"]["Channel"];
            /** Client */
            client: string;
            /** Identity Masked */
            identity_masked: string | null;
            state: components["schemas"]["SessionState"];
            /**
             * State Since
             * Format: date-time
             */
            state_since: string;
            title: components["schemas"]["Localized"];
            step_text: components["schemas"]["Localized"] | null;
            /** Line Count */
            line_count: number;
            /** Total Cents */
            total_cents: number | null;
            /** Flags */
            flags: components["schemas"]["CardFlag"][];
            next_step: components["schemas"]["Localized"] | null;
            /** Delivery Date */
            delivery_date?: string | null;
            /** Recipe Count */
            recipe_count?: number | null;
        };
        /** OrderStatusResponse */
        OrderStatusResponse: {
            /** Quote Id */
            quote_id: string;
            status: components["schemas"]["QuoteStatus"];
            /** Order Number */
            order_number: string | null;
            /** Replaced By Quote Id */
            replaced_by_quote_id: string | null;
        };
        /** OrderSummary */
        OrderSummary: {
            /** Session Id */
            session_id: string;
            /** Order Number */
            order_number: string | null;
            company: components["schemas"]["CompanyRef"];
            channel: components["schemas"]["Channel"];
            /** Client */
            client: string;
            /** Identity Masked */
            identity_masked: string | null;
            state: components["schemas"]["SessionState"];
            /**
             * State Since
             * Format: date-time
             */
            state_since: string;
            status_line: components["schemas"]["Localized"] | null;
            /** Delivery Date */
            delivery_date: string | null;
            /** Total Cents */
            total_cents: number | null;
            /** Requests */
            requests: components["schemas"]["SummaryRequest"][];
            /** Flags */
            flags: components["schemas"]["SummaryFlag"][];
            quote: components["schemas"]["QuoteRef"] | null;
            /** Signature Valid */
            signature_valid: boolean | null;
            agent?: components["schemas"]["AgentInfo"] | null;
        };
        /**
         * OverviewResponse
         * @description `GET /orders` and the stream's `snapshot` event.
         */
        OverviewResponse: {
            /**
             * Business Now
             * Format: date-time
             */
            business_now: string;
            totals: components["schemas"]["Totals"];
            /** Companies */
            companies: components["schemas"]["CompanyGroup"][];
        };
        /**
         * PhoneRequest
         * @description `POST /api/v1/me/phone`: the number of a hand-out account, set once.
         */
        PhoneRequest: {
            /** Phone E164 */
            phone_e164: string;
        };
        /** ProductHit */
        ProductHit: {
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
            /** Category */
            category: string;
            /** Sales Unit */
            sales_unit: string;
            sales_unit_label: components["schemas"]["Localized"];
            /** Image Url */
            image_url: string | null;
            /** Unit Price Gross */
            unit_price_gross: number | null;
            /** Price Per Base Unit */
            price_per_base_unit: number | null;
            /** Base Unit */
            base_unit: string | null;
            stock_status: components["schemas"]["StockStatus"];
            /** Available Date */
            available_date: string | null;
            /** Origin */
            origin: string | null;
        };
        /**
         * QuoteChange
         * @description What changed compared with the previous quote, after an edit or a requote.
         */
        QuoteChange: {
            /**
             * Reason
             * @enum {string}
             */
            reason: "edit" | "requote";
            /** Previous Total Cents */
            previous_total_cents: number;
            /** Line Ids */
            line_ids: string[];
            text: components["schemas"]["Localized"] | null;
        };
        /** QuoteLine */
        QuoteLine: {
            /** Line Id */
            line_id: string;
            /** Group */
            group: string | null;
            asked: components["schemas"]["AskedLine"];
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
            /** Image Url */
            image_url: string | null;
            /** Sales Unit */
            sales_unit: string;
            sales_unit_label: components["schemas"]["Localized"];
            /** Quantity Sales Units */
            quantity_sales_units: number;
            /** Quantity In Asked Unit */
            quantity_in_asked_unit: number;
            /** Unit Price Gross */
            unit_price_gross: number;
            /** Price Per Base Unit */
            price_per_base_unit: number | null;
            /** Base Unit */
            base_unit: string | null;
            /** Line Total Cents */
            line_total_cents: number;
            /**
             * Delivery Date
             * Format: date
             */
            delivery_date: string;
            stock_status: components["schemas"]["StockStatus"];
            /** Origin */
            origin: string | null;
            /** Reason Codes */
            reason_codes: string[];
            reason_text: components["schemas"]["Localized"];
            trace: components["schemas"]["Trace"];
            /** Alternatives */
            alternatives: components["schemas"]["Alternative"][];
        };
        /** QuoteRef */
        QuoteRef: {
            /** Id */
            id: string;
            /** Version */
            version: number;
            /** Hash */
            hash: string;
        };
        /**
         * QuoteResponse
         * @description The engine's decision plus the quote id, version, status, expiry and hash.
         */
        QuoteResponse: {
            decision: components["schemas"]["Decision"];
            /** Lines */
            lines: components["schemas"]["QuoteLine"][];
            /** Groups */
            groups: components["schemas"]["GroupSubtotal"][];
            /** Flags */
            flags: components["schemas"]["Flag"][];
            clarification: components["schemas"]["Clarification"] | null;
            /** Rejections */
            rejections: components["schemas"]["Rejection"][];
            /** Not Ordered */
            not_ordered: components["schemas"]["NotOrdered"][];
            /** Total Cents */
            total_cents: number;
            delivery: components["schemas"]["DeliverySummary"] | null;
            speak: components["schemas"]["Localized"];
            /** Rules Ref */
            rules_ref: string;
            /** Quote Id */
            quote_id: string;
            /** Version */
            version: number;
            /** Parent Quote Id */
            parent_quote_id: string | null;
            status: components["schemas"]["QuoteStatus"];
            /** Expires At */
            expires_at: string | null;
            /** Quote Hash */
            quote_hash: string | null;
        };
        /**
         * QuoteStatus
         * @description Quote lifecycle.
         *
         *     A quote starts as `ready`, `needs_clarification` or `rejected`, after the engine's
         *     decision. Only a `ready` quote can be sent for confirmation; the other two are
         *     answered or changed with `update_quote`.
         * @enum {string}
         */
        QuoteStatus: "ready" | "needs_clarification" | "rejected" | "pending_confirmation" | "confirmed" | "cancelled" | "expired" | "void";
        /** RankedCandidate */
        RankedCandidate: {
            /** Rank */
            rank: number;
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
            /** Price Per Base Unit */
            price_per_base_unit: number | null;
            stock_status: components["schemas"]["StockStatus"];
            /** Chosen */
            chosen: boolean;
        };
        /** Recipe */
        Recipe: {
            /** Recipe Id */
            recipe_id: string;
            /** Name */
            name: string;
            /** Image Url */
            image_url: string | null;
            /** Portions */
            portions: number;
            /** Ingredients */
            ingredients: components["schemas"]["RecipeIngredient"][];
        };
        /** RecipeHit */
        RecipeHit: {
            /** Recipe Id */
            recipe_id: string;
            /** Name */
            name: string;
            /** Image Url */
            image_url: string | null;
            /** Default Portions */
            default_portions: number;
            /** Diet Tags */
            diet_tags: string[];
        };
        /** RecipeIngredient */
        RecipeIngredient: {
            /** Index */
            index: number;
            /** Name */
            name: string;
            /** Quantity */
            quantity: number | null;
            /** Unit */
            unit: string | null;
            /** Product Id */
            product_id: string | null;
        };
        /** RecipeRef */
        RecipeRef: {
            /** Recipe Id */
            recipe_id: string;
            /** Portions */
            portions: number;
            /** Ingredient Index */
            ingredient_index: number;
        };
        /** Rejection */
        Rejection: {
            /** Line Id */
            line_id: string;
            /** Reason Code */
            reason_code: string;
            text: components["schemas"]["Localized"];
            next_step: components["schemas"]["Localized"];
        };
        /** RemoveLineEdit */
        RemoveLineEdit: {
            /** Quote Hash */
            quote_hash: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            op: "remove";
            /** Line Id */
            line_id: string;
        };
        /** RemovedProduct */
        RemovedProduct: {
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
        };
        /**
         * RequestedUnit
         * @description The unit the buyer asked in. With `package`, the word is in `package_word`.
         * @enum {string}
         */
        RequestedUnit: "l" | "kg" | "piece" | "sales_unit" | "package";
        /** SearchProductsResponse */
        SearchProductsResponse: {
            /** Results */
            results: components["schemas"]["ProductHit"][];
        };
        /** SearchRecipesResponse */
        SearchRecipesResponse: {
            /** Results */
            results: components["schemas"]["RecipeHit"][];
        };
        /**
         * SessionState
         * @description Session states, `docs/specs/dashboard.md` §4.
         * @enum {string}
         */
        SessionState: "in_conversation" | "needs_clarification" | "quote_ready" | "awaiting_confirmation" | "link_opened" | "confirmed" | "cancelled" | "expired" | "rejected" | "sms_failed" | "callback_requested" | "requote_needed" | "abandoned";
        /** SetQuantityEdit */
        SetQuantityEdit: {
            /** Quote Hash */
            quote_hash: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            op: "set_quantity";
            /** Line Id */
            line_id: string;
            /** Quantity */
            quantity: number;
        };
        /**
         * SignupRequest
         * @description `POST /api/v1/signup`: open sign-up for the connectors. Nothing is verified.
         *
         *     The email is lower-cased; the password needs at least 10 characters; `phone_e164` is
         *     read like the demo account's.
         */
        SignupRequest: {
            /** Email */
            email: string;
            /** Password */
            password: string;
            /** Phone E164 */
            phone_e164: string;
        };
        /**
         * StateGroup
         * @description The groups behind the counters and the `?state=` filter (#49, "States and totals").
         * @enum {string}
         */
        StateGroup: "active" | "waiting" | "confirmed" | "attention";
        /**
         * Step
         * @description One audit event without its payload, enough to verify the chain (§8.5).
         *
         *     The hash covers `session_id` and `quote_id` too (docs/audit-chain.md), so they are here.
         */
        Step: {
            /** Seq */
            seq: number;
            /** Order Index */
            order_index: number;
            /** Session Id */
            session_id: string;
            /** Quote Id */
            quote_id: string | null;
            /** At */
            at: string;
            /** Actor */
            actor: string;
            /** Type */
            type: string;
            text: components["schemas"]["Localized"];
            /** Payload Hash */
            payload_hash: string;
            /** Prev Hash */
            prev_hash: string;
            /** Session Prev Hash */
            session_prev_hash: string | null;
            /** Hash */
            hash: string;
        };
        /**
         * StockStatus
         * @enum {string}
         */
        StockStatus: "verified" | "unverified" | "unavailable";
        /** SummaryFlag */
        SummaryFlag: {
            /** Flag Key */
            flag_key: string;
            /** Code */
            code: string;
            text: components["schemas"]["Localized"];
            detail: components["schemas"]["Localized"] | null;
            /** Acknowledged At */
            acknowledged_at: string | null;
        };
        /**
         * SummaryLine
         * @description The fields of `QuoteLine` the summary shows, with the richer trace.
         */
        SummaryLine: {
            /** Line Id */
            line_id: string;
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
            /** Image Url */
            image_url: string | null;
            /** Sales Unit */
            sales_unit: string;
            sales_unit_label: components["schemas"]["Localized"];
            /** Quantity Sales Units */
            quantity_sales_units: number;
            /** Quantity In Asked Unit */
            quantity_in_asked_unit: number;
            /** Unit Price Gross */
            unit_price_gross: number;
            /** Price Per Base Unit */
            price_per_base_unit: number | null;
            /** Base Unit */
            base_unit: string | null;
            /** Line Total Cents */
            line_total_cents: number;
            /**
             * Delivery Date
             * Format: date
             */
            delivery_date: string;
            stock_status: components["schemas"]["StockStatus"];
            reason_text: components["schemas"]["Localized"];
            trace: components["schemas"]["SummaryTrace"];
        };
        /**
         * SummaryRequest
         * @description Assumed grouping: one request ("what was asked") with the lines added for it.
         */
        SummaryRequest: {
            /** Request Id */
            request_id: string;
            asked: components["schemas"]["AskedLine"];
            asked_text: components["schemas"]["Localized"];
            group: components["schemas"]["Localized"] | null;
            /** Lines */
            lines: components["schemas"]["SummaryLine"][];
            /** Not Ordered */
            not_ordered: components["schemas"]["NotOrdered"][];
        };
        /**
         * SummaryTrace
         * @description `Trace` plus the ranked candidates #49 lists for the summary.
         */
        SummaryTrace: {
            /** Found */
            found: number;
            /** Removed */
            removed: components["schemas"]["SummaryTraceRemoval"][];
            /** Left */
            left: number;
            ranking_rule: components["schemas"]["Localized"];
            /**
             * Ranked
             * @default []
             */
            ranked: components["schemas"]["RankedCandidate"][];
        };
        /**
         * SummaryTraceRemoval
         * @description `TraceRemoval` plus the products the filter removed.
         */
        SummaryTraceRemoval: {
            /** Reason Code */
            reason_code: string;
            /** Count */
            count: number;
            text: components["schemas"]["Localized"];
            /**
             * Products
             * @default []
             */
            products: components["schemas"]["RemovedProduct"][];
        };
        /**
         * Totals
         * @description Counts since `EVENT_START`, not limited by the filters or the 200-card cap.
         */
        Totals: {
            /** Active */
            active: number;
            /** Waiting */
            waiting: number;
            /** Confirmed */
            confirmed: number;
            /** Attention */
            attention: number;
            /** Confirmed Cents */
            confirmed_cents: number;
            /** By Channel */
            by_channel: {
                [key: string]: number;
            };
        };
        /**
         * Trace
         * @description Candidates found, removed per reason and left.
         *
         *     Each candidate is counted once, at the first check it fails, in the order the checks run.
         */
        Trace: {
            /** Found */
            found: number;
            /** Removed */
            removed: components["schemas"]["TraceRemoval"][];
            /** Left */
            left: number;
            ranking_rule: components["schemas"]["Localized"];
        };
        /** TraceRemoval */
        TraceRemoval: {
            /** Reason Code */
            reason_code: string;
            /** Count */
            count: number;
            text: components["schemas"]["Localized"];
        };
        /** TranscriptLine */
        TranscriptLine: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * Who
             * @enum {string}
             */
            who: "buyer" | "agent";
            /** Text */
            text: string;
            /**
             * Lang
             * @enum {string}
             */
            lang: "fi" | "en";
        };
        /** UsualItem */
        UsualItem: {
            /** Product Id */
            product_id: string;
            name: components["schemas"]["Localized"];
            /** Quantity */
            quantity: number;
            /** Unit */
            unit: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /**
         * VerifyResult
         * @description From #41's verify function; the global chain without `session_id`.
         */
        VerifyResult: {
            /** Ok */
            ok: boolean;
            /** Checked */
            checked: number;
            /** First Bad Seq */
            first_bad_seq: number | null;
            /** Signature Valid */
            signature_valid: boolean | null;
        };
        /**
         * ViewFlag
         * @description A contract flag plus what the confirmation adds to it.
         */
        ViewFlag: {
            /** Flag Key */
            flag_key: string;
            /** Code */
            code: string;
            /** Line Ids */
            line_ids: string[];
            /**
             * Kind
             * @enum {string}
             */
            kind: "acknowledge" | "choose";
            text: components["schemas"]["Localized"];
            /**
             * Options
             * @default []
             */
            options: components["schemas"]["FlagOption"][];
            /** Requires Ack */
            requires_ack: boolean;
            /** Acknowledged At */
            acknowledged_at: string | null;
            /** Current Option Id */
            current_option_id: string | null;
            /** Is New */
            is_new: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    search_products_api_v1_products_get: {
        parameters: {
            query: {
                q: string;
                claims?: components["schemas"]["Claim"][];
                category?: string | null;
                needed_by?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchProductsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_customer_context_api_v1_customer_context_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomerContext"];
                };
            };
        };
    };
    search_recipes_api_v1_recipes_get: {
        parameters: {
            query: {
                q: string;
                diet?: string[];
                occasion?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchRecipesResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_recipe_api_v1_recipes__recipe_id__get: {
        parameters: {
            query: {
                portions: number;
            };
            header?: never;
            path: {
                recipe_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Recipe"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    build_quote_api_v1_quotes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BuildQuoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    current_quote_api_v1_quotes_current_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteResponse"];
                };
            };
        };
    };
    get_quote_api_v1_quotes__quote_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                quote_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_quote_api_v1_quotes__quote_id__update_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                quote_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BuildQuoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_confirmation_api_v1_quotes__quote_id__confirmation_request_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                quote_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationRequestResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_order_status_api_v1_quotes__quote_id__status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                quote_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderStatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_orders_api_v1_public_orders_get: {
        parameters: {
            query?: {
                state?: components["schemas"]["StateGroup"] | null;
                channel?: components["schemas"]["Channel"] | null;
                since?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_order_api_v1_public_orders__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_steps_api_v1_public_orders__session_id__steps_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Step"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_transcript_api_v1_public_orders__session_id__transcript_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranscriptLine"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_events_api_v1_public_orders__session_id__events_get: {
        parameters: {
            query?: {
                download?: boolean;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEvent"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_verify_api_v1_public_audit_verify_get: {
        parameters: {
            query?: {
                session_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerifyResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_api_v1_public_stream_get: {
        parameters: {
            query?: {
                state?: components["schemas"]["StateGroup"] | null;
                channel?: components["schemas"]["Channel"] | null;
                since?: string | null;
            };
            header?: {
                "last-event-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_demo_account_api_v1_demo_accounts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoAccountRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoAccountResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_me_api_v1_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Me"];
                };
            };
        };
    };
    log_in_api_v1_session_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_session_api_v1_session_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    signup_api_v1_signup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Me"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_phone_api_v1_me_phone_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PhoneRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Me"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_inbox_api_v1_private_inbox_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxMessage"][];
                };
            };
        };
    };
    inbox_stream_api_v1_private_inbox_stream_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_request_api_v1_oauth_requests__request_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConnectRequestView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_api_v1_oauth_requests__request_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConnectDecision"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConnectRedirect"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_confirmation_api_v1_confirmations__token__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationView"];
                };
            };
            /** @description Unknown link */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    acknowledge_api_v1_confirmations__token__acknowledgements_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AcknowledgeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unknown link */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Stale quote, closed, or requoted */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Expired (production only) */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Not possible, or a flag unchecked */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
        };
    };
    edit_api_v1_confirmations__token__edits_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetQuantityEdit"] | components["schemas"]["RemoveLineEdit"] | components["schemas"]["ChooseAlternativeEdit"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unknown link */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Stale quote, closed, or requoted */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Expired (production only) */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Not possible, or a flag unchecked */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
        };
    };
    confirm_api_v1_confirmations__token__confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfirmRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmResponse"];
                };
            };
            /** @description Unknown link */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Stale quote, closed, or requoted */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Expired (production only) */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Not possible, or a flag unchecked */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
        };
    };
    cancel_api_v1_confirmations__token__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unknown link */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Stale quote, closed, or requoted */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Expired (production only) */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
            /** @description Not possible, or a flag unchecked */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationErrorDetail"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
}
