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
    "/api/v1/public/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Stream
         * @description Server-sent events: `snapshot` (as `GET /orders`), then `order_updated`, `step` and
         *     `transcript`. A reconnect with `Last-Event-ID` gets the missed events first.
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
        /** BuildQuoteRequest */
        BuildQuoteRequest: {
            /** Lines */
            lines: components["schemas"]["LineRequest"][];
        };
        /**
         * Channel
         * @description The channel a session came in through, one tile each on the overview.
         * @enum {string}
         */
        Channel: "phone" | "web_chat" | "webmcp" | "mcp";
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
         * StockStatus
         * @enum {string}
         */
        StockStatus: "verified" | "unverified" | "unavailable";
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
