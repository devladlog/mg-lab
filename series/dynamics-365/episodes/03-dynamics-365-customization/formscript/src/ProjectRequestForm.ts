/**
 * Project Request main form script (table mgl_projectrequest from episode 1).
 *
 * Only what a business rule can't do lives here:
 *  1. Look at OTHER records: warn when the customer account already has open requests (Xrm.WebApi).
 *  2. Depend on the form type: lock the business key (Request Code) once the record exists.
 * "Budget >= 50,000 needs a justification" is a business rule, not code (see README).
 *
 * Registered on the form as one OnLoad handler, "MGL.ProjectRequest.onLoad", with
 * "Pass execution context as first parameter". The OnChange handler is attached from onLoad with
 * addOnChange, so the form XML only ever references one function.
 */
namespace MGL.ProjectRequest {
    export const TABLE = "mgl_projectrequest";
    export const ACCOUNT = "mgl_customeraccountid";
    export const REQUEST_CODE = "mgl_requestcode";
    export const NOTE_ID = "mgl-open-requests";
    export const MAX_LISTED = 5;

    const FORM_TYPE_CREATE = 1; // getFormType(): 1 Create (also Quick Create), 2 Update, 3 Read Only, 4 Disabled

    export function onLoad(executionContext: Xrm.Events.EventContext): Promise<string[]> {
        const formContext = executionContext.getFormContext();

        // The episode 1 alternate key: editable only on create.
        const codeControl = formContext.getControl<Xrm.Controls.StringControl>(REQUEST_CODE);
        if (codeControl && formContext.ui.getFormType() !== FORM_TYPE_CREATE) {
            codeControl.setDisabled(true);
        }

        const account = formContext.getAttribute<Xrm.Attributes.LookupAttribute>(ACCOUNT);
        if (account) {
            account.addOnChange(onAccountChange);
        }
        return checkOpenRequests(formContext);
    }

    export function onAccountChange(executionContext: Xrm.Events.EventContext): Promise<string[]> {
        return checkOpenRequests(executionContext.getFormContext());
    }

    /** Shows (or clears) a form notification listing the account's other open requests. Never throws. */
    export async function checkOpenRequests(formContext: Xrm.FormContext): Promise<string[]> {
        formContext.ui.clearFormNotification(NOTE_ID);

        const account = formContext.getAttribute<Xrm.Attributes.LookupAttribute>(ACCOUNT);
        const value = account ? account.getValue() : null;
        if (!value || value.length === 0) {
            return [];
        }
        const accountId = cleanId(value[0].id);
        const selfId = cleanId(formContext.data.entity.getId()); // "" on a new record

        try {
            const result = await Xrm.WebApi.retrieveMultipleRecords(
                TABLE, buildOpenRequestsQuery(accountId, selfId), MAX_LISTED + 1);
            const codes = result.entities.map((e) => String(e[REQUEST_CODE]));
            if (codes.length > 0) {
                formContext.ui.setFormNotification(
                    formatMessage(value[0].name || "This account", codes), "WARNING", NOTE_ID);
            }
            return codes;
        } catch (e) {
            // A failed check must not block the user: say so quietly and carry on.
            const message = e && (e as { message?: string }).message ? (e as { message: string }).message : String(e);
            formContext.ui.setFormNotification(`Couldn't check open requests: ${message}`, "INFO", NOTE_ID);
            return [];
        }
    }

    /** OData options for Xrm.WebApi: active requests of the account, excluding the current record. */
    export function buildOpenRequestsQuery(accountId: string, selfId: string): string {
        let filter = `_${ACCOUNT}_value eq ${accountId} and statecode eq 0`;
        if (selfId) {
            filter += ` and ${TABLE}id ne ${selfId}`;
        }
        // Learn: encode the OData query string for special characters.
        return `?$select=${REQUEST_CODE}&$filter=${encodeURIComponent(filter)}&$orderby=${REQUEST_CODE}`;
    }

    export function formatMessage(accountName: string, codes: string[]): string {
        const shown = codes.slice(0, MAX_LISTED);
        const more = codes.length > MAX_LISTED ? " and more" : "";
        const noun = codes.length === 1 ? "open request" : "open requests";
        const count = codes.length > MAX_LISTED ? `${MAX_LISTED}+` : String(codes.length);
        return `${accountName} already has ${count} ${noun}: ${shown.join(", ")}${more}.`;
    }

    /** "{AAAA-...}" -> "aaaa-...": GUIDs from the form can come wrapped in braces; OData filters want them bare. */
    export function cleanId(id: string | null | undefined): string {
        return (id || "").replace(/[{}]/g, "").toLowerCase();
    }
}
