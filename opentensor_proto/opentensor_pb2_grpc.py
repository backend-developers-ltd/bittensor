# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

import opentensor_pb2 as opentensor__pb2


class OpentensorStub(object):
    """Missing associated documentation comment in .proto file"""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.Fwd = channel.unary_unary(
                '/Opentensor/Fwd',
                request_serializer=opentensor__pb2.FwdRequest.SerializeToString,
                response_deserializer=opentensor__pb2.FwdResponse.FromString,
                )
        self.Bwd = channel.unary_unary(
                '/Opentensor/Bwd',
                request_serializer=opentensor__pb2.BwdRequest.SerializeToString,
                response_deserializer=opentensor__pb2.BwdResponse.FromString,
                )


class OpentensorServicer(object):
    """Missing associated documentation comment in .proto file"""

    def Fwd(self, request, context):
        """Missing associated documentation comment in .proto file"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def Bwd(self, request, context):
        """Missing associated documentation comment in .proto file"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_OpentensorServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'Fwd': grpc.unary_unary_rpc_method_handler(
                    servicer.Fwd,
                    request_deserializer=opentensor__pb2.FwdRequest.FromString,
                    response_serializer=opentensor__pb2.FwdResponse.SerializeToString,
            ),
            'Bwd': grpc.unary_unary_rpc_method_handler(
                    servicer.Bwd,
                    request_deserializer=opentensor__pb2.BwdRequest.FromString,
                    response_serializer=opentensor__pb2.BwdResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'Opentensor', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class Opentensor(object):
    """Missing associated documentation comment in .proto file"""

    @staticmethod
    def Fwd(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/Opentensor/Fwd',
            opentensor__pb2.FwdRequest.SerializeToString,
            opentensor__pb2.FwdResponse.FromString,
            options, channel_credentials,
            call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def Bwd(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/Opentensor/Bwd',
            opentensor__pb2.BwdRequest.SerializeToString,
            opentensor__pb2.BwdResponse.FromString,
            options, channel_credentials,
            call_credentials, compression, wait_for_ready, timeout, metadata)
