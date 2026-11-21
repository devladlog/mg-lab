using System.ComponentModel.DataAnnotations;
using Grpc.Core;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Live;
using ProjectRequests.Api.Requests;
using ProjectRequests.Grpc;

namespace ProjectRequests.Api.Rpc;

/// <summary>
/// Episode 8: the same API, a second front door. Generated base class from requests.proto; one instance per call
/// (scoped, like a request), so the DbContext in the constructor is fine. Every async call takes
/// context.CancellationToken: it fires when the client cancels or its deadline passes.
/// </summary>
public sealed class RequestsGrpcService(
    RequestsDbContext db, TimeProvider clock, IRequestEvents events, ILogger<RequestsGrpcService> logger)
    : ProjectRequests.Grpc.Requests.RequestsBase
{
    public override async Task<RequestReply> GetRequest(GetRequestMessage request, ServerCallContext context)
    {
        if (request.Id <= 0)
            throw new RpcException(new Status(StatusCode.InvalidArgument, "Id must be a positive number."));

        var dto = await db.Requests.Where(r => r.Id == request.Id).Select(RequestEndpoints.ToDto)
            .FirstOrDefaultAsync(context.CancellationToken);

        // gRPC has status codes, not HTTP ones: NotFound travels in the trailers, the client gets an RpcException.
        return dto?.ToReply() ?? throw new RpcException(new Status(StatusCode.NotFound, $"Request {request.Id} not found."));
    }

    public override async Task ListRequests(
        ListRequestsMessage request, IServerStreamWriter<RequestReply> responseStream, ServerCallContext context)
    {
        var query = db.Requests.AsQueryable();
        if (!string.IsNullOrWhiteSpace(request.Department))
        {
            var code = request.Department.Trim().ToUpperInvariant();
            query = query.Where(r => r.Department.Code == code);
        }

        var sent = 0;
        await foreach (var dto in query.OrderBy(r => r.Id).Select(RequestEndpoints.ToDto).AsAsyncEnumerable()
                           .WithCancellation(context.CancellationToken))
        {
            await responseStream.WriteAsync(dto.ToReply(), context.CancellationToken);   // one message per row
            sent++;
        }
        logger.LogInformation("ListRequests streamed {Count} request(s) (department '{Department}')", sent, request.Department);
    }

    public override async Task<ImportReply> ImportRequests(
        IAsyncStreamReader<NewRequestMessage> requestStream, ServerCallContext context)
    {
        var reply = new ImportReply();
        await foreach (var message in requestStream.ReadAllAsync(context.CancellationToken))
        {
            var row = ++reply.Received;
            var input = message.ToCreateRequest();

            // Same rules as POST /api/requests: the attributes and IValidatableObject on CreateProjectRequest...
            var results = new List<ValidationResult>();
            if (!Validator.TryValidateObject(input, new ValidationContext(input), results, validateAllProperties: true))
            {
                foreach (var result in results)
                    reply.Errors.Add(new ImportError { Row = row, Field = result.MemberNames.FirstOrDefault() ?? "", Message = result.ErrorMessage ?? "" });
                continue;                                                   // a bad row doesn't stop the import
            }

            // ...and the same creation code (department check, priority, SignalR push to the live board).
            var (created, errors) = await RequestEndpoints.CreateCoreAsync(input, db, clock, events, context.CancellationToken);
            if (created is not null)
                reply.CreatedIds.Add(created.Id);
            else
                foreach (var (field, messages) in errors!)
                    foreach (var text in messages)
                        reply.Errors.Add(new ImportError { Row = row, Field = field, Message = text });
        }

        logger.LogInformation("ImportRequests: {Received} received, {Created} created, {Errors} error(s)",
            reply.Received, reply.CreatedIds.Count, reply.Errors.Count);
        return reply;
    }
}
