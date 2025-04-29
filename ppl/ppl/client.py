import asyncio
import hashlib
import json
import os

import ppl.packetDefinitions as pd

from datetime import datetime
from ipaddress import IPv4Address, ip_address
from jsonschema import validate
from jsonschema.exceptions import ValidationError, SchemaError
from typing import Tuple

from ppl.constants import SERVERPORT, SCHEMAPATH, SCHEMAPATHWHEEL
from ppl.enums import ConfigStorageMode
from ppl.exceptions import TimeoutError, ResponseError
from ppl.protocol import BaseMessage
from ppl.protocol import SubProtocol
from ppl.udpServer import UdpServer
from ppl.util import ts_print


class PplQuery:
    def __init__(self, udpServer : UdpServer, timeout):
        self.udpServer = udpServer
        self.timeout = timeout
        self.rx_address = Tuple[str, int]
        self.response = None
        self.error = None

    @staticmethod
    def _wait_for(event: asyncio.Event, timeout: float):
        return asyncio.wait_for(event.wait(), timeout)

    async def execute(
        self, data: bytes, address: IPv4Address, subProtocol: SubProtocol
    ) -> Tuple[bytes, Tuple[str, int]]:
        queryEvent = asyncio.Event()

        async def responseHandler(
            sequence: int, message: BaseMessage, address: Tuple[str, int]
        ) -> bool:
            if not isinstance(message, pd.GenericError):
                ts_print(f"GotResp: {subProtocol.get_subprotocol()}:  {repr(message)[13:]}")
            self.response = message
            self.rx_address = address
            queryEvent.set()
            return True
        
        with self.udpServer.subscriberFilterContext(
            responseHandler,
            filterAddr=str(address), filterSP=subProtocol.get_subprotocol()
        ):
            self.udpServer.sendPacket(data, address)
            try:
                await self._wait_for(queryEvent, self.timeout)
                queryEvent.clear()
            except asyncio.TimeoutError:
                contentStr = repr(subProtocol.packet_content)
                raise TimeoutError(f"{contentStr[13:contentStr.find('(')]}: No response in {self.timeout} seconds.")
        if isinstance(self.response, pd.GenericError):
            self.error = self.response.get("ErrorMsg")
            raise ResponseError(f"{subProtocol.get_subprotocol()}: {self.error}")
        assert self.response is not None
        return self.response, self.rx_address


class PplClient:
    def __init__(
        self,
        ownaddress: str = "0.0.0.0",
        ownport: int = SERVERPORT,
        timeout: int = 3,
    ):
        self.timeout = timeout
        self.queryLock = asyncio.Lock()
        self.udpServer = UdpServer(ownaddress, ownport)
        self.output = {'response': [], 'timestamp': [], 'message': []}

    def _handle_response(self, message: BaseMessage, addr: Tuple[str, int]):
        # handle response if neccessary
        return

    async def _send_command_and_handle_response(
        self, txdata: bytes, address: IPv4Address, subprotocol: SubProtocol
        ) -> dict:
        response, rx_address = await PplQuery(self.udpServer, self.timeout).execute(
            txdata, address, subprotocol
        )
        # result = self._handle_response(response, rx_address)
        return response, rx_address

    async def send_command(
        self,
        address: str,
        subprotocol: SubProtocol,
        logSucc: bool = True,
        logRespErr: bool = True,
        logTOError: bool = True,
        raiseRespException: bool = True,
        raiseTOException: bool = True
    ) -> dict:
        ip = ip_address(address)
        try:
            async with self.queryLock:
                ts_print(f"Executing {address}: {repr(subprotocol)}")
                data = self.udpServer.createPacket(subprotocol)
                message, rx_address = await self._send_command_and_handle_response(data, ip, subprotocol)
                if logSucc:
                    self._logSucc()
                return message, rx_address
        except ResponseError as e:
            if logRespErr:
                self._logErr(e.__str__())
            if raiseRespException:
                raise ResponseError(e.__str__())
        except TimeoutError as e:
            if logTOError:
                self._logErr(e.__str__())
            if raiseTOException:
                raise TimeoutError(e.__str__())


    # Commands
    def runCmdValidateJson(self, path):
        isValid, error = self._validateJson(path)
        if isValid == True:
            self._logSucc()
        else:
            self._logErr(error.__str__())
            
        return isValid
        
    async def runCmdTest(self, address, path, force_unpair, calledByConfigure = False):
        """Validate the json locally and then validate the MacConfig on the bridge"""
        error, device_config, networks = self._parseJson(path)
        if error is not None:
            self._logErr(f"Failed to validate json: {error.__str__()}")
            return []
        try:
            resp = []
            if force_unpair:
                await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logTOError=False, logSucc=False, raiseTOException=False)

            respPN = await self.send_command(address, pd.PairSubProt(pd.PairNode()), logSucc=False)

            macConfigs = self.udpServer.createPacketDataMacConfig(networks)
            i = 1
            for config in macConfigs:
                try:
                    await self.send_command(address, pd.ConfigSubProt(pd.ValidateMACConfig(**config)), logRespErr=False)
                    resp.append(True)
                except ResponseError as e:
                    resp.append(False)
                    self._logErr(f"Failed to validate config {i}. {e.__str__()}")
                except TimeoutError:
                    resp.append(False)
                    raise TimeoutError()
                finally:
                    i+=1

            if not calledByConfigure:
                await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False)
            return resp
        except ResponseError as e:
            return resp
        except TimeoutError:
            return resp

    async def runCmdClear(self, address, force_unpair):
        try:
            if force_unpair:
                await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False, logTOError=False, raiseTOException=False)
            await self.send_command(address, pd.PairSubProt(pd.PairNode()), logSucc=False)
            await self.send_command(address, pd.ConfigSubProt(pd.ClearConfigSet()), raiseRespException=False)
            await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False)
        except TimeoutError:
            return
        except ResponseError:
            return
        

    async def runCmdConfigure(self, address, force_unpair, skip_test, skip_clear, jsonPath):
        try:
            error, device_config, networks = self._parseJson(jsonPath)
            if error is not None:
                self._logErr(f"Failed to validate json: {error.__str__()}")
                return
            
            if not skip_test:
                isConfigValid = await self.runCmdTest(address, jsonPath, force_unpair, True)
                if len(isConfigValid) == 0:
                    return
                elif not all(isConfigValid):
                    await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False, raiseRespException=False, raiseTOException=False)
                    return
            else: 
                if force_unpair:
                    await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False, logTOError=False, raiseTOException=False)
                rspPair = await self.send_command(address, pd.PairSubProt(pd.PairNode()), logSucc=False)
                
            # reseting the output, so it is empty for the config calls 
            self.output = {'response': [], 'timestamp': [], 'message': []}
            
            globalHostConfig = self.udpServer.createPacketDataSetGlobalHostConfig(device_config)
            macConfigs = self.udpServer.createPacketDataMacConfig(networks)
            hostConfigs = self.udpServer.createPacketDataSetHostConfig(networks)
        
            if not skip_clear:
                rspCCS = await self.send_command(address, pd.ConfigSubProt(pd.ClearConfigSet()), logSucc=False)

            configSlots = [int(id) for id in networks]
            packet = pd.StartConfigSetTransaction(storage = ConfigStorageMode.PERSIST, slots=configSlots)
            rspSCST = await self.send_command(address, pd.ConfigSubProt(packet), logSucc=False)

            rspSGHC = await self.send_command(address, pd.ConfigSubProt(pd.SetGlobalHostConfig(**globalHostConfig)), logSucc=False)

            uid = self._getConfigUid(jsonPath)
            
            i = 0
            try: 
                for config in macConfigs:
                    rspSCS = await self.send_command(address, pd.ConfigSubProt(pd.SelectConfigSlot(slotid=configSlots[i])), logSucc=False)
                    rspSMC = await self.send_command(address, pd.ConfigSubProt(pd.SetMACConfig(**config)), logSucc=False)
                    rspSHC = await self.send_command(address, pd.ConfigSubProt(pd.SetHostConfig(**hostConfigs[i])), logSucc=False) 
                    rspFCS = await self.send_command(address, pd.ConfigSubProt(pd.FinalizeConfigSlot()), logSucc=False)
                    i += 1
                    self._logSucc()
            except ResponseError as e:
                self._logErr(e.__str__())
                if not 'rspSCS' in locals():
                    ...
                elif not 'rspSMC' in locals():
                    self.output['message'].append(f'Packet data: {(self.udpServer.createPacketDataMacConfig(networks, isOutput=True))[i]}')
                elif not 'rspSHC' in locals():
                    self.output['message'].append(f'Packet data: {(self.udpServer.createPacketDataSetHostConfig(networks, isOutput=True))[i]}')
                if not 'rspFCS' in locals():
                    ...

                if not len(macConfigs) == 1 and i > 0:
                    msg = "'ppl clear' highly recommended"
                    ts_print(msg)
                    self.output['message'].append(msg)
                    await self.send_command(address, pd.ConfigSubProt(pd.FinalizeConfigSlot()), logSucc=False, raiseRespException=False)
                 
            await self.send_command(address, pd.ConfigSubProt(pd.CommitConfigSet(UID=uid)), logSucc=False, raiseRespException=False)
            await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False)
        except ResponseError as e:
            if not 'rspPair' in locals():
                ...
            elif (not skip_clear and not 'rspCCS' in locals()) or not 'rspSCST' in locals():
                await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False, raiseRespException=False, raiseTOException=False)
            elif not 'rspSGHC' in locals():
                self.output['message'].append(f"Packet data: {self.udpServer.createPacketDataSetGlobalHostConfig(device_config, isOutput=True)}")
                message, _ = await self.send_command(address, pd.ConfigSubProt(pd.CommitConfigSet(UID=uid)), logSucc=False, raiseRespException=False, raiseTOException=False)
                if message is not None:
                    await self.send_command(address, pd.PairSubProt(pd.UnpairNode()), logSucc=False, raiseRespException=False, raiseTOException=False)
        except TimeoutError as e:
            return


    def _validateJson(self, jsonPath):
        try:
            isValid = False
            error = None
            json = self._loadJson(jsonPath)
            try:
                schema = self._loadJson(SCHEMAPATH)
            except FileNotFoundError as e:
                currentDir = os.path.dirname(__file__)
                fullPath = os.path.join(currentDir, SCHEMAPATHWHEEL) 
                schema = self._loadJson(fullPath)
            validate(json, schema)
            ts_print(f"Json at '{jsonPath}' successfully validated")
            isValid = True
        except FileNotFoundError as e:
            ts_print(f"Error during loading of json file: {e}")
            error = e
        except ValidationError as e:
            ts_print(f"Error: json data is invalid: {e}")
            error = e
        except SchemaError as e:
            ts_print(f"Error in json schema: {e}")
            error = e
        return isValid, error

    def _parseJson(self, jsonPath):
        isJsonValid, error = self._validateJson(jsonPath)
        if not isJsonValid:
            return error, False, False 
        
        data = self._loadJson(jsonPath)
        device_info = data['device']
        networks_info = data['networks']
        version_info = data['version']
        return error, device_info, networks_info

    def _loadJson(self, path):
        with open(path, 'r') as file:
            return json.load(file)

    def _getConfigUid(self, jsonPath):
        with open(jsonPath, 'rb') as file:
            file_contents = file.read()
            md5_hash = hashlib.md5(file_contents).hexdigest()
            return abs(int(md5_hash, 16)) & 0xFFFFFFFFFFFFFFFF
    
    def _logSucc(self):
        self.output['response'].append("OK")
        self.output['timestamp'].append(datetime.strftime(datetime.now(), "%H:%M:%S"))

    def _logErr(self, message: str):
        self.output['response'].append("ERROR")
        self.output['message'].append(message)
        self.output['timestamp'].append(datetime.strftime(datetime.now(), "%H:%M:%S"))
